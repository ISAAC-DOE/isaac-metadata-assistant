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
 */

import type { Page } from '@playwright/test';

const TOL = 1;

/*
 * NOTE on visibility, duplicated verbatim inside both `page.evaluate` bodies
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
}

/**
 * Does the DOCUMENT scroll horizontally?
 *
 * This is the assertion the brief names explicitly:
 * `document.documentElement.scrollWidth <= clientWidth`. A wide table or code
 * block is allowed to scroll *inside its own container*; the page body is not.
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

/**
 * Text that is CLIPPED — i.e. cut off by an ancestor's `overflow: hidden`
 * with no ellipsis and no scrollbar, so the characters are simply gone.
 *
 * Two things are explicitly NOT defects and are not reported:
 *
 *   * deliberate single-line truncation (`text-overflow: ellipsis`);
 *   * content inside a SCROLLABLE region (`overflow: auto | scroll`). This one
 *     matters more than it sounds: this app nests `main.screen-main`
 *     (`overflow: auto`) inside `div.screen-card` (`overflow: hidden`), so a
 *     naive ancestor walk reports every below-the-fold paragraph as "clipped by
 *     .screen-card". The walk is therefore per-axis and STOPS at the first
 *     scrollable ancestor: whatever is inside it is reachable by scrolling.
 */
export async function findClippedText(page: Page, root = 'body'): Promise<Offender[]> {
  return page.evaluate(
    ({ rootSel, tol }) => {
      const out: { selector: string; detail: string; text: string }[] = [];
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

      for (const el of Array.from(container.querySelectorAll<HTMLElement>('*'))) {
        const text = ownText(el);
        if (!text) continue;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        if (!rendered(el)) continue;
        const own = getComputedStyle(el);

        // Per-axis walk. `liveX`/`liveY` go false as soon as that axis is
        // resolved — either by a scrollable ancestor (reachable, stop looking)
        // or by a reported clip.
        let liveX = true;
        let liveY = true;
        const ellipsised = own.textOverflow === 'ellipsis';

        for (let a = el.parentElement; a && (liveX || liveY); a = a.parentElement) {
          const st = getComputedStyle(a);
          const ar = a.getBoundingClientRect();

          if (liveX) {
            if (st.overflowX === 'auto' || st.overflowX === 'scroll') {
              liveX = false;
            } else if (st.overflowX === 'hidden' || st.overflowX === 'clip') {
              const truncated = ellipsised || st.textOverflow === 'ellipsis';
              if (!truncated && (rect.right > ar.right + tol || rect.left < ar.left - tol)) {
                out.push({
                  selector: describe(el),
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
    { rootSel: root, tol: TOL }
  );
}

/**
 * OVERLAP, measured the way it actually harms a user: is any interactive
 * control covered by something else?
 *
 * Pairwise box-intersection over every element is mathematically "overlap" but
 * is meaningless in a CSS-grid app (every ancestor overlaps its children). What
 * matters is occlusion: hit-test the control's own visible centre and check the
 * topmost element there belongs to the control.
 *
 * Two refinements, both learned from false positives this probe produced on
 * the real app:
 *
 *   1. The hit-test point is the centre of the control's VISIBLE INTERSECTION
 *      with every clipping/scrolling ancestor, not the centre of its layout
 *      box. Without that, a control scrolled out of view inside `aside.trail`
 *      (319px tall over 1286px of content) reports as "occluded by main" —
 *      which is just "it is scrolled away", not a defect.
 *   2. A candidate is RE-TESTED after `scrollIntoView({ block: 'center' })`.
 *      Content sitting under a panel at one scroll offset, and reachable by
 *      scrolling, is normal; only a control that is STILL covered once it has
 *      been scrolled into view is genuinely unreachable, which is the thing
 *      worth failing a build over.
 *
 * Controls with no visible area at all are skipped, so callers should invoke
 * this at more than one scroll position.
 */
export async function findObscuredControls(page: Page): Promise<Offender[]> {
  return page.evaluate(() => {
    const SEL = 'a[href], button, input, select, textarea, [role="tab"], [role="radio"], [tabindex]:not([tabindex="-1"])';
    const out: { selector: string; detail: string; text: string }[] = [];
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

    for (const el of Array.from(document.querySelectorAll<HTMLElement>(SEL))) {
      if (!rendered(el)) continue;
      const st = getComputedStyle(el);
      if (st.pointerEvents === 'none') continue;
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      // Hit-test the centre of what is ACTUALLY visible. A control that is
      // entirely scrolled away or clipped away has nothing to hit-test and is
      // not an occlusion finding.
      const clear = (target: HTMLElement) => {
        const v = visibleRect(target);
        if (v.width < 2 || v.height < 2) return { ok: null as boolean | null, x: 0, y: 0, hit: null as Element | null };
        const x = v.left + v.width / 2;
        const y = v.top + v.height / 2;
        const hit = document.elementFromPoint(x, y);
        if (!hit) return { ok: null, x, y, hit };
        if (hit === target || target.contains(hit) || hit.contains(target)) return { ok: true, x, y, hit };
        // A <label> that forwards its click to the control is not occlusion.
        if (hit instanceof HTMLLabelElement && hit.control === target) return { ok: true, x, y, hit };
        return { ok: false, x, y, hit };
      };

      const first = clear(el);
      if (first.ok !== false) continue;

      // Second chance: scroll it into view, exactly as a user (or Playwright's
      // own auto-scroll before a click) would, and re-test.
      el.scrollIntoView({ block: 'center', inline: 'center' });
      const second = clear(el);
      if (second.ok !== false) continue;

      out.push({
        selector: describe(el),
        detail: `still occluded after scrollIntoView: centre (${Math.round(second.x)},${Math.round(
          second.y
        )}) hit ${describe(second.hit!)} instead`,
        text: (el.textContent ?? '').trim().slice(0, 60),
      });
    }
    return out;
  });
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

export function render(offenders: Offender[]): string {
  return offenders.map((o) => `  - ${o.selector}: ${o.detail}\n      text: ${JSON.stringify(o.text)}`).join('\n');
}
