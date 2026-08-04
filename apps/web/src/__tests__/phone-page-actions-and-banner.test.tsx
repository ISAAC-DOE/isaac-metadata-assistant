/*
 * I1 (the New Record action was off screen on /experiments) and I2 (the
 * needs-attention banner rendered an 88px column).
 *
 * MEASURED, 375x812, production build, Chromium:
 *
 *   I1 · `.page-header` ALREADY had `flex-wrap: wrap` and `min-width: 0` at
 *        ≤640px, so the header was not the cause and is not touched here.
 *        `.page-actions` is `display: flex; flex: none` with computed
 *        `flex-wrap: nowrap` and `min-width: auto`; its three buttons measured
 *        125.3 + 174.8 + 127.6 plus 20px of gaps = 447.7px inside a 297px
 *        header, so "New Record" ran 359.1→486.7 — 122px past the 364px content
 *        edge and 111.7px past the viewport. AFTER: `.page-actions` w=297,
 *        scrollWidth 297, the three buttons at x=39 right=336 on three rows, and
 *        the page's `pastRight` list (elements painting past the viewport) went
 *        from 4 entries to 0. At 320x568: 447.7 → 242, likewise 0.
 *
 *   I2 · the banner is a row flex with `.needsyou-icon { flex: none }`,
 *        `.needsyou-body { flex: 1 }` and `.needsyou-action { flex: none }`;
 *        the action reserved 151.7px of a 297px banner, leaving the body
 *        w=88.2 h=465.2 in a banner 499.2px tall. AFTER: body 227 x 187.6,
 *        banner 272.6 tall. At 320x568: body 204 wide, banner 344.3 tall.
 *
 * HONESTY NOTE: jsdom lays nothing out and evaluates no media query. The
 * numbers above are browser evidence; the assertions below are either
 * "CSS source:" (the declaration is read out of the stylesheet with ?raw) or
 * DOM assertions that the elements those selectors target are really produced.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import {
  EXP_ID,
  bundleRoutes,
  healthSynthetic,
  stubFetchRoutes,
  tutorialSessionRoutes,
} from '../test/apiFixtures';
import { LABELS } from '../lib/labels';
import { __resetTutorialStore } from '../lib/tutorialController';

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

function rulesIn(block: string): { selector: string; body: string }[] {
  return [...block.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    selector: m[1].trim().replace(/\s+/g, ' '),
    body: m[2],
  }));
}

const ruleIn = (block: string, selector: string): string | undefined =>
  rulesIn(block).find((r) => r.selector === selector)?.body;

const screens = cssByName('screens.css');
const phone = mediaBlock(screens, '(max-width: 640px)');

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('I1 · the page actions can wrap inside a phone-width header', () => {
  it('CSS source: .page-actions is re-declared at ≤640px and may wrap', () => {
    const body = ruleIn(phone, '.page-actions');
    expect(body, '.page-actions must be re-declared at ≤640px').toBeDefined();
    expect(body!).toMatch(/flex-wrap:\s*wrap/);
    // `flex: none` + `min-width: auto` is exactly what made a 447.7px row
    // unshrinkable; both are overridden.
    expect(body!).toMatch(/min-width:\s*0/);
    expect(body!).toMatch(/flex:\s*1 1 100%/);
  });

  it('CSS source: each action owns its line rather than being squeezed', () => {
    const body = ruleIn(phone, '.page-actions > *');
    expect(body, 'the action children must be re-declared at ≤640px').toBeDefined();
    expect(body!).toMatch(/flex:\s*1 1 auto/);
  });

  it('CSS source: the desktop row is untouched', () => {
    const base = rulesIn(stripComments(screens)).find((r) => r.selector === '.page-actions')!;
    expect(base.body).toMatch(/display:\s*flex/);
    expect(base.body).toMatch(/flex:\s*none/);
    expect(base.body).not.toMatch(/flex-wrap/);
  });

  it('CSS source: the header rule that was NOT the cause is left alone', () => {
    // `.page-header { flex-wrap: wrap }` already existed at ≤640px and is not
    // the defect; re-"fixing" it would have changed nothing and hidden the real
    // cause. It must still be there, and must not have grown a workaround.
    const header = ruleIn(phone, '.page-header');
    expect(header, '.page-header must keep its existing ≤640px rule').toBeDefined();
    expect(header!).toMatch(/flex-wrap:\s*wrap/);
    expect(header!).not.toMatch(/display:\s*block/);
  });

  it('DOM: the page actions are direct children of .page-actions', async () => {
    /*
     * P1 changed WHAT this row holds; D2 changed WHERE it is. Neither changed the
     * property under test.
     *
     * P1: the screen used to render three controls — Reset Demo, Run Synthetic Demo
     * and a "New Record" button that navigated to the same route as the one beside it
     * and promised a capability the build does not have. The duplicate is gone.
     *
     * D2: both remaining controls act on the built-in example records, and both of
     * their endpoints now REQUIRE a worked-example session header and refuse without
     * one — so on the ordinary My Experiments they were dead controls. They moved
     * together into the persistent worked-example bar, and `.page-actions` moved with
     * them: it is still the row that holds them, reused rather than duplicated,
     * precisely so the ≤640px rules asserted above keep governing these two buttons.
     *
     * The measured 447.7px overflow in the header comment above was a THREE-button
     * row; that measurement is history and is left as written. It is not re-derived
     * here (jsdom lays nothing out), and this test never claimed it — it asserts
     * only that `.page-actions > *` has real direct children to target.
     *
     * `/api/health` is stubbed synthetic-only on purpose: without it the reset
     * control is (correctly, fail-closed) absent and this row would hold ONE child,
     * which would let the direct-child assertion pass on a single element.
     */
    stubFetchRoutes({
      ...tutorialSessionRoutes(),
      ...bundleRoutes(),
      'GET /api/health': { body: healthSynthetic },
    });
    const view = renderAt('/experiments');
    const { container } = view;
    // Enter the session the bar — and therefore this row — is gated on.
    fireEvent.click(await view.findByRole('button', { name: LABELS.actionStartTutorial }));
    await waitFor(() => expect(container.querySelector('.page-actions')).not.toBeNull());
    const actions = container.querySelector('.page-actions')!;
    await waitFor(() => expect(actions.children.length).toBeGreaterThanOrEqual(2));
    const children = [...actions.children];
    for (const child of children) expect(child.tagName).toBe('BUTTON');
    const labels = children.map((c) => c.textContent?.trim());
    expect(labels).toContain(LABELS.actionResetDemo);
    expect(labels).toContain(LABELS.actionRunDemo);
    // and nothing here offers record creation, which this build cannot do
    expect(labels.join(' ')).not.toMatch(/new record/i);
    __resetTutorialStore();
    sessionStorage.clear();
  });

  /*
   * ADDED WITH THE MOVE, because the move created a way for the four CSS-source
   * assertions above to go vacuous: `.page-actions` is now rendered ONLY by the
   * worked-example bar, so a slice that stopped rendering the bar would leave them
   * describing a selector nothing uses — green, and about nothing. This pins the other
   * half of the arrangement, which is also the D1 property that the ordinary My
   * Experiments offers no example-workspace action at all.
   */
  it('DOM: .page-actions is absent in the ordinary workspace', async () => {
    stubFetchRoutes({ ...bundleRoutes(), 'GET /api/health': { body: healthSynthetic } });
    const view = renderAt('/experiments');
    // wait for the loaded screen, so this cannot pass on a page that has not rendered
    await view.findByRole('button', { name: LABELS.actionStartTutorial });
    expect(view.container.querySelector('.page-actions')).toBeNull();
    expect(view.queryByRole('button', { name: LABELS.actionResetDemo })).toBeNull();
    expect(view.queryByRole('button', { name: LABELS.actionRunDemo })).toBeNull();
  });
});

describe('I2 · the needs-attention banner breaks its row instead of squeezing', () => {
  it('CSS source: the banner is allowed to wrap at ≤640px', () => {
    const body = ruleIn(phone, '.needsyou-banner');
    expect(body, '.needsyou-banner must be re-declared at ≤640px').toBeDefined();
    expect(body!).toMatch(/flex-wrap:\s*wrap/);
  });

  it('CSS source: the body keeps a usable basis and the action takes its own line', () => {
    const body = ruleIn(phone, '.needsyou-body');
    expect(body, '.needsyou-body must be re-declared at ≤640px').toBeDefined();
    // A basis, not just `flex: 1` — `flex: 1` against a 151.7px sibling is what
    // produced the 88px column.
    expect(body!).toMatch(/flex:\s*1 1 \d+px/);
    expect(body!).toMatch(/min-width:\s*0/);

    const action = ruleIn(phone, '.needsyou-action');
    expect(action, '.needsyou-action must be re-declared at ≤640px').toBeDefined();
    expect(action!).toMatch(/flex:\s*1 0 100%/);
  });

  it('CSS source: the desktop banner is untouched', () => {
    const base = rulesIn(stripComments(screens)).find((r) => r.selector === '.needsyou-banner')!;
    expect(base.body).toMatch(/display:\s*flex/);
    expect(base.body).not.toMatch(/flex-wrap/);
  });

  it('DOM: .needsyou-action is the control itself, and a direct child of the banner', async () => {
    stubFetchRoutes(bundleRoutes());
    const { container } = renderAt(`/record/${EXP_ID}`);
    await waitFor(() => expect(container.querySelector('.needsyou-banner')).not.toBeNull());
    const banner = container.querySelector('.needsyou-banner')!;
    const action = banner.querySelector('.needsyou-action')!;
    const body = banner.querySelector('.needsyou-body')!;
    // `flex: 1 0 100%` only reaches the button if the class is ON the button and
    // the button is a flex ITEM of the banner — not wrapped in a div.
    expect(action.tagName).toBe('BUTTON');
    expect(action.parentElement).toBe(banner);
    expect(body.parentElement).toBe(banner);
    // and the banner still carries the whole pending story it was squeezing
    expect(banner.querySelector('.needsyou-title')).not.toBeNull();
    expect(banner.querySelector('.needsyou-text')).not.toBeNull();
    expect(banner.querySelectorAll('.needsyou-list li').length).toBeGreaterThan(0);
  });
});
