/*
 * I5 — "What Can I Ask?" showed a fold that could land immediately after a
 * category heading, so a POPULATED category read as empty.
 *
 * MEASURED before (Chromium, production build, /record/<id>, desktop rail):
 *   1280x800 · panel 270px (max-height 34vh) · catalog scrollport 114px against
 *              a 475px scrollHeight · 424.5px of viewport free ABOVE the panel.
 *              Group heads at listTop 0, 89, 178.1, 267.1, 356.2, 413.2; the
 *              SECOND heading ("Missing Fields and Confirmations") was fully
 *              visible while its first example (bottom 138.1) was not.
 *   1280x600 · panel 202px · list 46px — the FIRST heading's own first example
 *              was already cut.
 *
 * MEASURED after, same build:
 *   1280x800 · panel 334px · list 178px · every visible heading's first example
 *              fully visible · panel top y=88.5 (inside the viewport) · Close
 *              and the trigger both reachable.
 *   1280x600 · panel 250px · list 94px · likewise.
 *   1440x900 · list 220px · 1920x1080 · list 262px (the px co-cap binding).
 *
 * WHY THE NARROW DEFAULT IS UNCHANGED. Sweeping 22 viewport/mount pairs
 * (320x480 … 1920x1080, record rail and Project Memory), the space above the
 * popover is 38.7%–76.5% of the viewport, and EVERY case where a larger cap ran
 * past the TOP edge was a drawer mount at width ≤ 768 — worst 320x568, where
 * only 219.8px exists above it. Clipping there is unrecoverable, because the top
 * edge is outside this popover's own scrollport. So the larger cap is scoped to
 * the desktop rail (the assistant collapses into the drawer at ≤1024px), and the
 * narrow default stays at 34vh. After scoping: 0 of 22 pairs clipped.
 *
 * WHY A SIZE CHANGE IS NOT ENOUGH ON ITS OWN. The scrollport height is a
 * function of the viewport, so for some viewport heights a fully visible heading
 * still has zero pixels of its first example below it — measured, that still
 * happens at 414x736 in the drawer. Hence the second channel: a local-background
 * scroll shadow, painted only while there IS more below. Pixel-verified in the
 * browser by screenshotting the list's bottom 8px strip twice, once as rendered
 * and once with the background removed, and comparing the raw PNG buffers:
 *   1280x800 (rail)   scrollTop 0 → differs (shadow paints); at end → identical
 *   414x736 (drawer)  scrollTop 0 → differs (shadow paints); at end → identical
 *
 * HONESTY NOTE: jsdom evaluates no media query, lays nothing out and rasterises
 * nothing. Every assertion below is either a CSS-source guard or a DOM
 * assertion; the geometry and the pixels above are the browser evidence.
 */

import { describe, it, expect } from 'vitest';
import { fireEvent, render } from '@testing-library/react';

import { AssistantPanel } from '../components/AssistantPanel';
import { CAPABILITIES_TRIGGER_LABEL } from '../lib/assistantCapabilities';
import type { AssistantMessage } from '../lib/types';

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const cssByName = (name: string): string =>
  Object.entries(cssFiles).find(([path]) => path.endsWith(`/${name}`))?.[1] ?? '';

const stripComments = (source: string): string => source.replace(/\/\*[\s\S]*?\*\//g, '');

function mediaBlock(source: string, query: string): string {
  const src = stripComments(source);
  const bodies: string[] = [];
  let from = 0;
  for (;;) {
    const start = src.indexOf(`@media ${query}`, from);
    if (start < 0) break;
    const open = src.indexOf('{', start);
    let depth = 0;
    let closed = -1;
    for (let i = open; i < src.length; i += 1) {
      if (src[i] === '{') depth += 1;
      else if (src[i] === '}') {
        depth -= 1;
        if (depth === 0) {
          closed = i;
          break;
        }
      }
    }
    if (closed < 0) break;
    bodies.push(src.slice(open + 1, closed));
    from = closed;
  }
  return bodies.join('\n');
}

function rulesIn(source: string): { selector: string; body: string }[] {
  return [...stripComments(source).matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    selector: m[1].trim().replace(/\s+/g, ' '),
    body: m[2],
  }));
}

/** Everything OUTSIDE any at-rule: each `@…{…}` block is removed by brace
 *  matching (splitting on the first `@media` would silently drop the rest of the
 *  file, which has several). */
function withoutAtRules(source: string): string {
  const src = stripComments(source);
  let out = '';
  for (let i = 0; i < src.length; i += 1) {
    if (src[i] !== '@') {
      out += src[i];
      continue;
    }
    const open = src.indexOf('{', i);
    if (open < 0) break;
    let depth = 0;
    let j = open;
    for (; j < src.length; j += 1) {
      if (src[j] === '{') depth += 1;
      else if (src[j] === '}') {
        depth -= 1;
        if (depth === 0) break;
      }
    }
    i = j;
  }
  return out;
}

const assistant = cssByName('assistant.css');
const baseRules = rulesIn(withoutAtRules(assistant));
const ruleFor = (selector: string): string | undefined =>
  baseRules.find((r) => r.selector === selector)?.body;

const REPLY: AssistantMessage = { text: 'Two fields still need you.', answeredFrom: 'workflow' };

function open() {
  const view = render(<AssistantPanel reply={REPLY} prompts={[]} experimentId="01EXPA" recordRev={5} />);
  fireEvent.click(view.getByRole('button', { name: CAPABILITIES_TRIGGER_LABEL }));
  return { ...view, dialog: view.getByRole('dialog', { name: CAPABILITIES_TRIGGER_LABEL }) };
}

describe('I5 · the capability catalog gets the height the viewport actually has', () => {
  it('CSS source: the narrow/drawer default is still the viewport-safe 34vh', () => {
    const panel = ruleFor('.assistant-capabilities-panel');
    expect(panel, 'assistant.css must declare .assistant-capabilities-panel').toBeDefined();
    const cap = /max-height:\s*(\d+(?:\.\d+)?)vh/.exec(panel!);
    expect(cap, 'the narrow default must stay a plain vh cap').not.toBeNull();
    expect(Number(cap![1])).toBeLessThanOrEqual(34);
  });

  it('CSS source: the desktop RAIL gets a larger, still-bounded cap', () => {
    // NOTE: assistant-capabilities.test.tsx's own max-height guard regexes the
    // FIRST `.assistant-capabilities-panel` rule — the narrow default above — so
    // it does not see this override. This is where the override is pinned.
    const rail = mediaBlock(assistant, '(min-width: 1025px)');
    expect(rail, 'the rail override must live at min-width: 1025px — the width at which the assistant stops being the drawer').not.toBe('');
    const body = rulesIn(rail).find((r) => r.selector === '.assistant-capabilities-panel')?.body;
    expect(body, 'the override must re-declare the popover cap').toBeDefined();

    // Still viewport-bounded: a vh term…
    const vh = /min\(\s*(\d+(?:\.\d+)?)vh/.exec(body!);
    expect(vh, 'the cap must remain viewport-relative').not.toBeNull();
    expect(Number(vh![1])).toBeGreaterThan(34); // it is genuinely larger…
    expect(Number(vh![1])).toBeLessThanOrEqual(46); // …and below the value this rule was previously lowered FROM

    // …and an absolute co-cap, because the space above the popover stops growing
    // with the viewport (it plateaued at 458.5px in the sweep).
    const px = /,\s*(\d+)px\s*\)/.exec(body!);
    expect(px, 'the cap must also have an absolute ceiling').not.toBeNull();
    expect(Number(px![1])).toBeLessThanOrEqual(440);
  });

  it('CSS source: the list is still the ONE scroll region, and can still shrink', () => {
    const list = ruleFor('.assistant-capabilities-list')!;
    expect(list).toMatch(/overflow-y:\s*auto/);
    expect(list).toMatch(/overflow-x:\s*hidden/);
    expect(list).toMatch(/min-height:\s*0/);
    expect(list).toMatch(/flex:\s*1 1 auto/);
    // the popover itself stays bounded and never scrolls sideways
    expect(ruleFor('.assistant-capabilities-panel')!).toMatch(/overflow-x:\s*hidden/);
  });

  it('CSS source: a continuation cue is painted, and only while there is more', () => {
    const list = ruleFor('.assistant-capabilities-list')!;
    // The local-background scroll-shadow idiom: two `local` cover layers that
    // scroll WITH the content (so the cue disappears at each end) and two
    // `scroll` shadow layers pinned to the scrollport.
    expect(list).toMatch(/background:/);
    expect((list.match(/\blocal\b/g) ?? []).length).toBe(2);
    expect((list.match(/\bscroll\b/g) ?? []).length).toBe(2);
    expect((list.match(/radial-gradient/g) ?? []).length).toBe(2);
  });

  it('CSS source: the cue adds no motion (reduced-motion stays honoured)', () => {
    const list = ruleFor('.assistant-capabilities-list')!;
    expect(list).not.toMatch(/animation/);
    expect(list).not.toMatch(/transition/);
    expect(list).not.toMatch(/animation-timeline/);
  });

  it('CSS source: the deliberately scrollable empty-state region is NOT regressed', () => {
    // assistant.css's `.assistant-empty` shrink contract is intentional and is
    // asserted by assistant-layout.test.tsx; nothing here may undo it.
    const empty = ruleFor('.assistant-empty')!;
    expect(empty).toMatch(/flex:\s*0 1 auto/);
    expect(empty).toMatch(/min-height:\s*0/);
    expect(empty).toMatch(/overflow-y:\s*auto/);
  });

  it('DOM: no category is really empty — an empty-looking one is always a fold', () => {
    const { dialog } = open();
    const groups = [...dialog.querySelectorAll('.assistant-capabilities-group')];
    expect(groups.length).toBeGreaterThan(1);
    for (const group of groups) {
      const heading = group.querySelector('.assistant-capabilities-eyebrow');
      expect(heading?.textContent?.trim()).toBeTruthy();
      // Every heading ships at least one example, so "this category looks empty"
      // can only ever be a scroll artefact — which is what the height and the
      // continuation cue address.
      expect(group.querySelectorAll('button.assistant-capabilities-example').length).toBeGreaterThan(0);
      // …and the heading is immediately followed by its first example, so the
      // only gap the fold can land in is the one the cue covers.
      expect(heading!.nextElementSibling?.classList.contains('assistant-capabilities-example')).toBe(
        true,
      );
    }
  });

  it('DOM: trigger and dismiss controls are both present with the panel open', () => {
    const { dialog, getByRole } = open();
    expect(getByRole('button', { name: CAPABILITIES_TRIGGER_LABEL }).getAttribute('aria-expanded')).toBe('true');
    expect(dialog.querySelector('.assistant-capabilities-close')).not.toBeNull();
    // the honesty sentences stay OUTSIDE the scroll region, as before
    const list = dialog.querySelector('.assistant-capabilities-list')!;
    for (const p of dialog.querySelectorAll('.assistant-capabilities-note, .assistant-capabilities-boundary')) {
      expect(list.contains(p)).toBe(false);
    }
  });
});
