/*
 * F7 — the graph's mode was chosen ONCE, at mount.
 *
 * `defaultGraphMode()` has always said a 220-node canvas is not a phone surface
 * below 860px, and that decision was right: a fresh load at 390 or 320 renders
 * no `<svg>` at all. But it ran only in the initial reducer state, so a reader
 * who RESIZED a wide window down — or rotated a tablet — stayed in Explore.
 *
 * MEASURED in headless Chromium ON DARWIN (so, per `e2e/a11y-baseline.ts`'s
 * standing rule, indicative — CI's Linux column is the authority for any px
 * figure): Project Memory → Graph opened at 1280 in Explore with an `<svg>`
 * present, then resized to 320, still held 206 nodes on the canvas, drawn at
 * 9.3–10.8px each. The sweep that commissioned this work reported 3 × 3px nodes
 * with 102 of them having their centre stolen by the fixed Assistant trigger;
 * this run measured the same defect at a larger node size, and the size is not
 * the point — Explore persisting below its own usability threshold is.
 *
 * These tests drive the real screen through the real reducer. `jsdom` has no
 * `matchMedia`, which is why the whole file installs a controllable stub: that
 * absence is also what makes every OTHER test in the suite open in Explore.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, act, type RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { ProjectMemory } from '../screens/ProjectMemory';
import {
  NARROW_GRAPH_VIEWPORT_QUERY,
  defaultGraphMode,
  isNarrowGraphViewport,
} from '../lib/graphCommands';
import { stubFetchRoutes, graphStatusUnavailable, memoryGraphAvailable } from '../test/apiFixtures';

const graphRoutes = {
  'GET /api/graph/status': { body: graphStatusUnavailable },
  'GET /api/memory/graph': { body: memoryGraphAvailable },
};

/**
 * The other media queries this screen legitimately asks, answered honestly
 * rather than folded into a permissive catch-all — see `installViewport`.
 *
 * These are the complete set of `matchMedia` consumers this render reaches:
 * `AssistantPanel`'s `prefersReducedMotion` (`:408`) and `AssistantDrawer`'s
 * desktop check (`:94`). The Assistant rail is part of Project Memory, so both
 * are hit by every render below. Both are answered `false`, which is the honest
 * jsdom answer: no reduced-motion preference, and no measurable viewport.
 *
 * They are enumerated because the strict stub threw on each in turn, which is
 * the guard doing its job. A fourth consumer will announce itself the same way.
 */
const PASSTHROUGH_QUERIES = ['(prefers-reduced-motion: reduce)', '(min-width: 1024px)'] as const;

/**
 * A `matchMedia` whose `matches` we control and whose `change` listeners we can
 * fire, standing in for the browser's viewport.
 *
 * It answers exactly two queries — the graph's own, and the reduced-motion one
 * above — and THROWS on anything else. That is deliberate: a permissive stub
 * returning `false` for every query would let this file keep passing if the
 * production code started asking a DIFFERENT question about the viewport, and
 * "the code no longer consults the viewport" is precisely the regression these
 * tests exist to catch. A new query here should be a decision, announced by a
 * red test, not absorbed silently.
 */
function installViewport(initiallyNarrow: boolean) {
  const listeners = new Set<(e: MediaQueryListEvent) => void>();
  const state = { narrow: initiallyNarrow, removed: 0 };

  const mql = {
    get matches() {
      return state.narrow;
    },
    media: NARROW_GRAPH_VIEWPORT_QUERY,
    addEventListener: (_type: string, fn: (e: MediaQueryListEvent) => void) => listeners.add(fn),
    removeEventListener: (_type: string, fn: (e: MediaQueryListEvent) => void) => {
      state.removed += 1;
      listeners.delete(fn);
    },
    addListener: (fn: (e: MediaQueryListEvent) => void) => listeners.add(fn),
    removeListener: (fn: (e: MediaQueryListEvent) => void) => listeners.delete(fn),
    onchange: null,
    dispatchEvent: () => true,
  };

  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => {
      if (query === NARROW_GRAPH_VIEWPORT_QUERY) return mql as unknown as MediaQueryList;
      if ((PASSTHROUGH_QUERIES as readonly string[]).includes(query)) {
        return {
          matches: false,
          media: query,
          addEventListener: () => {},
          removeEventListener: () => {},
          addListener: () => {},
          removeListener: () => {},
          onchange: null,
          dispatchEvent: () => true,
        } as unknown as MediaQueryList;
      }
      throw new Error(
        `unexpected media query ${JSON.stringify(query)} — this stub answers only ` +
          `${JSON.stringify(NARROW_GRAPH_VIEWPORT_QUERY)} and ${PASSTHROUGH_QUERIES.join(', ')}`
      );
    })
  );

  return {
    /** Move the viewport across the threshold and notify subscribers, as a resize does. */
    resizeTo(narrow: boolean) {
      state.narrow = narrow;
      act(() => {
        for (const fn of [...listeners]) fn({ matches: narrow } as MediaQueryListEvent);
      });
    },
    get listenerCount() {
      return listeners.size;
    },
    get removeCount() {
      return state.removed;
    },
  };
}

/**
 * THE SAME STUB WITH THE MODERN API REMOVED — `addListener`/`removeListener`
 * only, as older WebKit exposes.
 *
 * REVIEW FINDING, 2026-08-25: `MemoryGraphCard`'s legacy branch was UNREACHABLE
 * from this file, because `installViewport` always supplies `addEventListener`,
 * so `typeof mql.addEventListener === 'function'` was true on every render and
 * the fallback's cleanup had no coverage at all. A subscription that is never
 * released is exactly the leak the modern path is tested against; the fallback
 * deserves the same test.
 *
 * This is COVERAGE, not a fix — the fallback was correct before this stub
 * existed, and these tests pass in both directions. What they close is the
 * possibility of the fallback rotting unnoticed.
 */
function installLegacyViewport(initiallyNarrow: boolean) {
  const listeners = new Set<(e: MediaQueryListEvent) => void>();
  const state = { narrow: initiallyNarrow, removed: 0 };

  const mql = {
    get matches() {
      return state.narrow;
    },
    media: NARROW_GRAPH_VIEWPORT_QUERY,
    // DELIBERATELY ABSENT: addEventListener / removeEventListener.
    addListener: (fn: (e: MediaQueryListEvent) => void) => listeners.add(fn),
    removeListener: (fn: (e: MediaQueryListEvent) => void) => {
      state.removed += 1;
      listeners.delete(fn);
    },
    onchange: null,
    dispatchEvent: () => true,
  };

  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => {
      if (query === NARROW_GRAPH_VIEWPORT_QUERY) return mql as unknown as MediaQueryList;
      if ((PASSTHROUGH_QUERIES as readonly string[]).includes(query)) {
        return {
          matches: false,
          media: query,
          addEventListener: () => {},
          removeEventListener: () => {},
          addListener: () => {},
          removeListener: () => {},
          onchange: null,
          dispatchEvent: () => true,
        } as unknown as MediaQueryList;
      }
      throw new Error(`unexpected media query ${JSON.stringify(query)}`);
    })
  );

  return {
    resizeTo(narrow: boolean) {
      state.narrow = narrow;
      act(() => {
        for (const fn of [...listeners]) fn({ matches: narrow } as MediaQueryListEvent);
      });
    },
    get listenerCount() {
      return listeners.size;
    },
    get removeCount() {
      return state.removed;
    },
    get hasModernApi() {
      return typeof (mql as { addEventListener?: unknown }).addEventListener === 'function';
    },
  };
}

function renderGraphTab(initialEntry = '/memory?tab=graph') {
  const view = render(
    <MemoryRouter
      initialEntries={[initialEntry]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ProjectMemory />
    </MemoryRouter>
  );
  fireEvent.click(view.getByRole('tab', { name: 'Graph' }));
  return view;
}

/** Which of the two mode radios is selected right now. */
const selectedMode = (view: RenderResult): string | null => {
  for (const name of ['Explore', 'Browse']) {
    const radio = view.queryByRole('radio', { name });
    if (radio?.getAttribute('aria-checked') === 'true' || (radio as HTMLInputElement | null)?.checked) {
      return name;
    }
  }
  return null;
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the narrow-viewport rule is a live question, not a mount-time one', () => {
  it('isNarrowGraphViewport reads the current viewport every time it is called', () => {
    const vp = installViewport(false);
    expect(isNarrowGraphViewport()).toBe(false);
    expect(defaultGraphMode()).toBe('explore');

    vp.resizeTo(true);
    // THE CORE OF F7. Before the fix there was no way to ask this question after
    // mount at all; the answer was baked into the initial reducer state.
    expect(isNarrowGraphViewport()).toBe(true);
    expect(defaultGraphMode()).toBe('browse');
  });

  it('answers false, not true, when there is no viewport to measure', () => {
    // jsdom and SSR have no `matchMedia`. "No viewport" must not be reported as
    // "narrow viewport" — that would silently put every server render and every
    // other test in this suite into Browse.
    vi.stubGlobal('matchMedia', undefined);
    expect(isNarrowGraphViewport()).toBe(false);
    expect(defaultGraphMode()).toBe('explore');
  });
});

describe('resizing a wide window down leaves Explore', () => {
  it('switches Explore → Browse when the viewport crosses below the threshold', async () => {
    const vp = installViewport(false);
    stubFetchRoutes(graphRoutes);
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });

    expect(selectedMode(view), 'a wide viewport opens in Explore').toBe('Explore');

    vp.resizeTo(true);

    expect(
      selectedMode(view),
      'after the viewport crossed below 860px the canvas is no longer a view of anything, ' +
        'so the surface must have moved to Browse'
    ).toBe('Browse');
  });

  it('and subscribes exactly once, releasing the subscription on unmount', async () => {
    const vp = installViewport(false);
    stubFetchRoutes(graphRoutes);
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });

    expect(vp.listenerCount).toBe(1);
    view.unmount();
    expect(vp.listenerCount).toBe(0);
    expect(vp.removeCount).toBeGreaterThan(0);
  });
});

describe('the coercion is ONE-DIRECTIONAL, and that asymmetry is the decision', () => {
  /*
   * Coerce AWAY from a render that is not a view of anything; never coerce INTO
   * one. Widening the window back must not force Explore: a wide viewport in
   * Browse can only have got there by a deliberate act — a click, or a shared
   * `?gmode=browse` link — and overriding that would be this same bug with the
   * sign flipped.
   */
  it('widening back does not force Explore on someone who chose Browse', async () => {
    const vp = installViewport(false);
    stubFetchRoutes(graphRoutes);
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });

    fireEvent.click(view.getByRole('radio', { name: 'Browse' }));
    expect(selectedMode(view)).toBe('Browse');

    vp.resizeTo(true);
    expect(selectedMode(view), 'narrowing must not disturb a Browse the reader already chose').toBe('Browse');

    vp.resizeTo(false);
    expect(
      selectedMode(view),
      'widening back must leave a deliberately-chosen Browse alone — the mode is a preference, ' +
        'and only an unusable render justifies overriding it'
    ).toBe('Browse');
  });

  it('a narrow viewport that stays narrow does not fight a reader who insists on Explore', async () => {
    const vp = installViewport(true);
    stubFetchRoutes(graphRoutes);
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });

    expect(selectedMode(view), 'a narrow viewport opens in Browse').toBe('Browse');

    // The reader asks for the canvas anyway. That is their call to make, and the
    // fix must not turn the mode toggle into a control that does nothing.
    fireEvent.click(view.getByRole('radio', { name: 'Explore' }));
    expect(selectedMode(view)).toBe('Explore');

    // A `change` event that reports the SAME narrow state — which a real browser
    // does not send, but a re-layout can — must not undo that choice either.
    vp.resizeTo(true);
    expect(selectedMode(view)).toBe('Explore');
  });
});

describe('a resize is not a navigational act', () => {
  it('does not write the graph parameters into the URL', async () => {
    const vp = installViewport(false);
    stubFetchRoutes(graphRoutes);
    const view = renderGraphTab('/memory?tab=graph');
    await view.findByText('Graph', { selector: 'h2' });

    vp.resizeTo(true);
    expect(selectedMode(view)).toBe('Browse');

    // `gmode` is written only by an explicit navigational act (a typed command or
    // an applied Assistant proposal). Dragging a window must not push a history
    // entry, or Back would "undo" a resize.
    expect(window.location.search).not.toContain('gmode');
  });
});

describe('the legacy addListener fallback subscribes and releases too', () => {
  it('the stub really has no modern API, or this suite proves nothing', () => {
    const vp = installLegacyViewport(false);
    expect(
      vp.hasModernApi,
      'if the stub grows addEventListener, these tests silently exercise the modern path — ' +
        'which is exactly the gap this file had'
    ).toBe(false);
  });

  it('coerces Explore → Browse through addListener, and removes the listener on unmount', async () => {
    const vp = installLegacyViewport(false);
    stubFetchRoutes(graphRoutes);
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });

    expect(vp.listenerCount, 'the fallback must subscribe exactly once').toBe(1);
    expect(selectedMode(view)).toBe('Explore');

    vp.resizeTo(true);
    expect(selectedMode(view), 'the fallback must coerce exactly as the modern path does').toBe(
      'Browse'
    );

    view.unmount();
    expect(vp.listenerCount, 'a subscription that outlives the component is the leak').toBe(0);
    expect(vp.removeCount).toBeGreaterThan(0);
  });
});

describe('the coercion ANNOUNCES itself, and does not leave a stale line describing Explore', () => {
  /*
   * REVIEW FINDING, 2026-08-25. The coercion called `setState` directly rather
   * than going through `dispatch`, and `applyGraphAction`'s `setMode` case
   * attaches no notice and CLEARS none — so the mode changed under the reader
   * with nothing said, and any line the previous command had put in the polite
   * live region stayed there describing a view that no longer existed.
   *
   * THE DECISION, argued rather than assumed: a NOTICE, not documented silence.
   * The mode is a control the reader can operate, and this is the one case where
   * something other than the reader operates it — silently overriding a
   * deliberate act is the class of defect this repository has spent several
   * sessions removing. The announcement goes in the SAME single polite region
   * (`memory-graph-live`), in the lowest-precedence `commandOutcome` slot, whose
   * stated purpose is a terse outcome the reducer left no notice on. No second
   * live region is created — the render site forbids it.
   *
   * WHAT STAYS SILENT, and why that is not inconsistent: no URL write and no
   * COMMAND-HISTORY entry. `?gmode=` is written by navigational acts only, or
   * Back would "undo" a resize; and the history list is a list of COMMANDS, so
   * a row for something nobody typed would misdescribe itself. Announcing an
   * event and recording it as a user action are different claims.
   */
  const liveRegion = (view: RenderResult): string =>
    view.container.querySelector('.memory-graph-live')?.textContent?.trim() ?? '';

  it('says a narrow viewport moved the reader to Browse', async () => {
    const vp = installViewport(false);
    stubFetchRoutes(graphRoutes);
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });
    expect(liveRegion(view), 'nothing has happened yet').toBe('');

    vp.resizeTo(true);

    expect(selectedMode(view)).toBe('Browse');
    const announced = liveRegion(view);
    expect(
      announced,
      'the mode changed without the reader asking; the polite live region must say so'
    ).not.toBe('');
    expect(announced).toMatch(/Browse/);
    // The threshold is named, so the announcement explains itself rather than
    // just reporting that something moved.
    expect(announced).toMatch(/860/);
  });

  it('and clears the line a previous command left behind', async () => {
    const vp = installViewport(false);
    stubFetchRoutes(graphRoutes);
    const view = renderGraphTab();
    await view.findByText('Graph', { selector: 'h2' });

    const input = view.getByRole('combobox', { name: 'Graph command' });
    // A REAL verb, so this exercises the `commandOutcome` slot rather than the
    // `commandError` one. `find` is one of the seven verbs whose only
    // announcement IS that slot.
    fireEvent.change(input, { target: { value: 'find export' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(selectedMode(view)).toBe('Explore');
    const afterCommand = liveRegion(view);
    expect(afterCommand, 'the command must have announced something to make this test mean anything').not.toBe('');

    vp.resizeTo(true);

    expect(selectedMode(view)).toBe('Browse');
    expect(
      liveRegion(view),
      'the previous command described a view the reader no longer has — leaving it standing is ' +
        'the honesty defect, not merely untidy'
    ).not.toBe(afterCommand);
    expect(liveRegion(view)).toMatch(/Browse/);
  });
});
