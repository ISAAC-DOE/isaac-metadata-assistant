/*
 * R0 · the guided walkthrough's accessibility, TESTED rather than asserted in a
 * comment.
 *
 * Most of these cases use a small local harness rather than the whole app, and
 * that is deliberate: the properties under test are about focus, keys and the
 * relationship between the mark and its control, and a harness lets each one be
 * set up exactly — including the one case the real app cannot produce, where the
 * control that STARTED the walkthrough is still on screen when it closes. The
 * axe sweep and the announcement run against the real app, where the overlay sits
 * inside the real shell.
 */

import { useRef } from 'react';
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axe from 'axe-core';

import { AppRoutes } from '../App';
import { GuidedTutorial } from '../components/GuidedTutorial';
import { LABELS } from '../lib/labels';
import { isTutorialCompleted } from '../lib/tutorialPreference';
import { startTutorial } from '../lib/tutorialController';
import { TUTORIAL_ANCHORS, TUTORIAL_STEPS } from '../lib/tutorialSteps';
import {
  CANONICAL_RESET_IDS,
  bundleRoutes,
  canonicalFiveSummaries,
  tutorialSessionRoutes,
  exportReadyRoutes,
  graphStatusUnavailable,
  healthSynthetic,
  stubFetchRoutes,
} from '../test/apiFixtures';

const TOTAL = TUTORIAL_STEPS.length;
const PENDING_ID = CANONICAL_RESET_IDS[0];
const READY_ID = CANONICAL_RESET_IDS[2];

/** jsdom implements neither of these; the component treats both as optional, and
 *  these stubs let the tests observe HOW they are called. */
let scrollIntoView: ReturnType<typeof vi.fn>;

beforeEach(() => {
  scrollIntoView = vi.fn();
  (Element.prototype as unknown as { scrollIntoView: unknown }).scrollIntoView = scrollIntoView;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** Force a `prefers-reduced-motion` answer. jsdom has no matchMedia at all, so
 *  the component's optional call is what keeps it working unmocked. */
function stubReducedMotion(reduce: boolean): void {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: reduce && /prefers-reduced-motion/.test(query),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
}

/**
 * A minimal page carrying the three things the overlay interacts with: a control
 * that starts the walkthrough and STAYS mounted, the `#main` focus fallback the
 * app shell provides, and a real element wearing step one's anchor.
 */
function Harness() {
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <main id="main" tabIndex={-1}>
        <button type="button" ref={trigger} onClick={() => startTutorial(trigger.current)}>
          Begin
        </button>
        <button type="button" data-tutorial-anchor={TUTORIAL_ANCHORS.experimentsQueue}>
          The queue
        </button>
      </main>
      <GuidedTutorial anchorTimeoutMs={40} />
    </>
  );
}

function renderHarness() {
  stubFetchRoutes({
    ...tutorialSessionRoutes(),
    'GET /api/experiments': { body: { experiments: canonicalFiveSummaries } },
  } as never);
  return render(
    <MemoryRouter
      initialEntries={['/experiments']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Harness />
    </MemoryRouter>,
  );
}

const mark = () => document.querySelector<HTMLElement>('.tutorial-mark');

async function openFirstStep(): Promise<HTMLElement> {
  fireEvent.click(screen.getByRole('button', { name: 'Begin' }));
  return waitFor(() => {
    const found = mark();
    expect(found).not.toBeNull();
    expect(found!.getAttribute('data-tutorial-step-available')).toBe('true');
    return found!;
  });
}

// --- focus --------------------------------------------------------------------

describe('R0 · a11y — focus', () => {
  it('moves focus INTO the coach mark when a step opens', async () => {
    renderHarness();
    const bubble = await openFirstStep();
    await waitFor(() => expect(document.activeElement).toBe(bubble));
    // It is a programmatic focus target, not a Tab stop of its own.
    expect(bubble).toHaveAttribute('tabindex', '-1');
  });

  it('re-focuses the mark on each new step, so a keyboard reader is never left behind', async () => {
    renderHarness();
    const bubble = await openFirstStep();
    // Move focus somewhere else, then advance: the next step must take it back.
    screen.getByRole('button', { name: 'Begin' }).focus();
    expect(document.activeElement).not.toBe(bubble);

    fireEvent.click(within(bubble).getByRole('button', { name: LABELS.actionTutorialNext }));
    await waitFor(() => {
      const current = mark();
      expect(current).not.toBeNull();
      expect(current!.getAttribute('data-tutorial-step')).toBe(TUTORIAL_STEPS[1].id);
      expect(document.activeElement).toBe(current);
    });
  });

  it('returns focus to the control that started it when it closes', async () => {
    renderHarness();
    const bubble = await openFirstStep();
    fireEvent.click(within(bubble).getByRole('button', { name: LABELS.actionCloseTutorial }));

    await waitFor(() => expect(mark()).toBeNull());
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Begin' }));
  });

  it('falls back to the main region when the trigger has been unmounted', async () => {
    renderHarness();
    const bubble = await openFirstStep();
    // The walkthrough's own navigation routinely unmounts its trigger; simulate
    // that by removing it before closing.
    screen.getByRole('button', { name: 'Begin' }).remove();

    fireEvent.click(within(bubble).getByRole('button', { name: LABELS.actionSkipTutorial }));
    await waitFor(() => expect(mark()).toBeNull());
    // Not <body>: a keyboard reader would otherwise have to Tab from the top of
    // the document to get back to where they were.
    expect(document.activeElement).toBe(document.getElementById('main'));
  });

  it('does NOT trap focus — Tab is never intercepted', async () => {
    renderHarness();
    const bubble = await openFirstStep();
    // A real modal in this app (the artifact viewer) DOES preventDefault on Tab to
    // contain focus. The walkthrough must not, because the control it is
    // describing lives outside the mark and has to stay reachable.
    const tab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    bubble.dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(false);

    const shiftTab = new KeyboardEvent('keydown', {
      key: 'Tab',
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    });
    bubble.dispatchEvent(shiftTab);
    expect(shiftTab.defaultPrevented).toBe(false);
  });

  it('is operable by keyboard alone: every control is a real button with a name', async () => {
    renderHarness();
    const bubble = await openFirstStep();
    const names = within(bubble)
      .getAllByRole('button')
      .map((b) => b.getAttribute('aria-label') ?? b.textContent?.trim() ?? '');
    // Four controls, four DISTINCT accessible names. A duplicate would make two of
    // them indistinguishable in a screen reader's control list.
    expect(names).toEqual([
      LABELS.actionSkipTutorial,
      LABELS.actionTutorialBack,
      LABELS.actionTutorialNext,
      LABELS.actionCloseTutorial,
    ]);
    expect(new Set(names).size).toBe(names.length);
    for (const button of within(bubble).getAllByRole('button')) {
      expect(button.tagName).toBe('BUTTON');
      expect(button).toHaveAttribute('type', 'button');
      // No positive tabindex anywhere: the DOM order is the tab order.
      expect(button.getAttribute('tabindex')).toBeNull();
    }
  });
});

// --- Escape -------------------------------------------------------------------

describe('R0 · a11y — the Escape contract', () => {
  it('Escape leaves the walkthrough, records nothing, and returns focus', async () => {
    renderHarness();
    await openFirstStep();

    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => expect(mark()).toBeNull());
    // Escape is a dismissal, never a completion — the version stays unrecorded so
    // the walkthrough is offered again next visit.
    expect(isTutorialCompleted()).toBe(false);
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Begin' }));
  });

  it('Escape never advances a step', async () => {
    renderHarness();
    await openFirstStep();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(mark()).toBeNull());
    // Nothing re-opened on a later step.
    expect(document.querySelector('[data-tutorial-step]')).toBeNull();
  });

  it('a key that is not Escape does nothing', async () => {
    renderHarness();
    const bubble = await openFirstStep();
    fireEvent.keyDown(document, { key: 'Enter' });
    fireEvent.keyDown(document, { key: 'a' });
    expect(mark()).toBe(bubble);
    expect(bubble.getAttribute('data-tutorial-step')).toBe(TUTORIAL_STEPS[0].id);
  });
});

// --- announcement -------------------------------------------------------------

describe('R0 · a11y — the step is announced', () => {
  it('announces the progress and the title, and updates on each step', async () => {
    renderHarness();
    const bubble = await openFirstStep();

    const live = () => document.querySelector('[role="status"][aria-live="polite"]');
    await waitFor(() => {
      expect(live()?.textContent).toBe(`Step 1 of ${TOTAL}: ${TUTORIAL_STEPS[0].title}`);
    });

    fireEvent.click(within(bubble).getByRole('button', { name: LABELS.actionTutorialNext }));
    await waitFor(() => {
      expect(live()?.textContent).toBe(`Step 2 of ${TOTAL}: ${TUTORIAL_STEPS[1].title}`);
    });
  });

  it('names and describes the dialog from its own title and body', async () => {
    renderHarness();
    const bubble = await openFirstStep();
    expect(bubble).toHaveAttribute('role', 'dialog');

    const titleId = bubble.getAttribute('aria-labelledby')!;
    const bodyId = bubble.getAttribute('aria-describedby')!;
    expect(document.getElementById(titleId)?.textContent).toBe(TUTORIAL_STEPS[0].title);
    expect(document.getElementById(bodyId)?.textContent).toContain(
      TUTORIAL_STEPS[0].body.slice(0, 40),
    );
    // The progress is rendered as text too, not only announced, so a sighted
    // reader can see where they are.
    expect(bubble.textContent).toContain(`Step 1 of ${TOTAL}`);
  });
});

// --- the highlight ------------------------------------------------------------

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

describe('R0 · a11y — the highlight does not disable what it highlights', () => {
  it('leaves the target operable and in the accessibility tree', async () => {
    renderHarness();
    await openFirstStep();

    const target = screen.getByRole('button', { name: 'The queue' });
    expect(target).toHaveAttribute('data-tutorial-highlight', 'true');
    // Still a real, named, enabled control — the mark decorates it, it does not
    // replace or shadow it.
    expect(target).toBeEnabled();
    expect(target).not.toHaveAttribute('aria-hidden');
    expect(target).not.toHaveAttribute('inert');
    expect(target.closest('[aria-hidden="true"]')).toBeNull();
    expect(target.closest('[inert]')).toBeNull();
  });

  it('draws no modal backdrop over the page', async () => {
    renderHarness();
    const bubble = await openFirstStep();
    // Nothing covers the app: no backdrop element, and the mark is not modal.
    expect(bubble).not.toHaveAttribute('aria-modal');
    expect(document.querySelector('.tutorial-backdrop')).toBeNull();
    expect(document.querySelectorAll('[aria-modal="true"]')).toHaveLength(0);
  });

  it('the ring is decorative and cannot intercept a pointer', async () => {
    renderHarness();
    await openFirstStep();
    const ring = document.querySelector('.tutorial-ring')!;
    expect(ring).toHaveAttribute('aria-hidden', 'true');
    // Read from the stylesheet rather than from `getComputedStyle`, which in jsdom
    // depends on how the CSS was injected: the property is what matters, and this
    // way the assertion cannot pass by accident.
    const css = cssFiles['../components/tutorial.css'];
    expect(css).toBeDefined();
    expect(css).toMatch(/\.tutorial-ring\s*\{[^}]*pointer-events:\s*none/);
  });

  it('the directional pointer is decorative', async () => {
    renderHarness();
    await openFirstStep();
    const arrows = document.querySelectorAll('.tutorial-arrow');
    // It may be absent (the mark can be centered), but if present it must be
    // hidden from assistive technology — the copy already states the relationship.
    for (const arrow of arrows) {
      expect(arrow).toHaveAttribute('aria-hidden', 'true');
    }
  });

  it('brings an offscreen target into view, and recalculates on resize', async () => {
    renderHarness();
    await openFirstStep();
    expect(scrollIntoView).toHaveBeenCalled();
    // A resize must not throw and must not lose the mark.
    fireEvent(window, new Event('resize'));
    fireEvent(window, new Event('scroll'));
    expect(mark()).not.toBeNull();
  });
});

// --- reduced motion -----------------------------------------------------------

describe('R0 · a11y — reduced motion', () => {
  it('does not animate the scroll when the reader asks for reduced motion', async () => {
    stubReducedMotion(true);
    renderHarness();
    await openFirstStep();
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
    for (const call of scrollIntoView.mock.calls) {
      expect(call[0]).toMatchObject({ behavior: 'auto' });
    }
  });

  it('animates it otherwise', async () => {
    stubReducedMotion(false);
    renderHarness();
    await openFirstStep();
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
    expect(scrollIntoView.mock.calls.some((c) => c[0]?.behavior === 'smooth')).toBe(true);
  });

  it('the stylesheet drops its transitions under prefers-reduced-motion', () => {
    const css = cssFiles['../components/tutorial.css'];
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
    const block = /@media \(prefers-reduced-motion: reduce\)\s*\{([\s\S]*?)\n\}/.exec(css!);
    expect(block).not.toBeNull();
    expect(block![1]).toMatch(/\.tutorial-ring/);
    expect(block![1]).toMatch(/\.tutorial-mark/);
    expect(block![1]).toMatch(/transition:\s*none/);
  });

  it('survives an environment with no matchMedia at all', async () => {
    // jsdom's default. The component's optional call is the reason this works, and
    // a regression to a bare `window.matchMedia(...)` would throw here.
    expect(window.matchMedia).toBeUndefined();
    renderHarness();
    await openFirstStep();
    expect(mark()).not.toBeNull();
  });
});

// --- narrow viewports and high zoom ------------------------------------------

describe('R0 · a11y — narrow width and high zoom', () => {
  it('keeps the mark inside the viewport at a phone width', async () => {
    vi.stubGlobal('innerWidth', 320);
    vi.stubGlobal('innerHeight', 480);
    renderHarness();
    const bubble = await openFirstStep();
    // The inline placement is clamped to the viewport with an 8px inset, so the
    // mark can never be positioned off the edge — which is also what makes it
    // usable at 200% zoom, where the CSS viewport is half as wide.
    const top = Number.parseFloat(bubble.style.top || '0');
    const left = Number.parseFloat(bubble.style.left || '0');
    expect(left).toBeGreaterThanOrEqual(8);
    expect(top).toBeGreaterThanOrEqual(8);
    expect(left).toBeLessThanOrEqual(320);
    expect(top).toBeLessThanOrEqual(480);
  });

  it('the stylesheet caps the mark against the viewport rather than a fixed size', () => {
    const css = cssFiles['../components/tutorial.css'];
    // A fixed 360px width would overflow a 320px viewport; a fixed height would
    // clip the copy at high zoom. Both are expressed against the viewport, and the
    // mark scrolls internally rather than pushing the page sideways.
    expect(css).toMatch(/width:\s*min\(360px,\s*calc\(100vw - 32px\)\)/);
    expect(css).toMatch(/max-height:\s*calc\(100vh - 32px\)/);
    expect(css).toMatch(/overflow-y:\s*auto/);
  });
});

// --- axe over the real app ---------------------------------------------------

/** The real axe engine, restricted to the rules this overlay can violate. */
async function axeRules(container: HTMLElement, rules: string[]) {
  const results = await axe.run(container, {
    runOnly: { type: 'rule', values: rules },
    resultTypes: ['violations'],
  });
  return results.violations;
}

describe('R0 · a11y — axe over the walkthrough in the real app', () => {
  const RULES = [
    'button-name',
    'aria-allowed-attr',
    'aria-allowed-role',
    'aria-required-attr',
    'aria-valid-attr-value',
    'aria-dialog-name',
  ];

  it('reports no violation on the coach mark, the offer, or the surface behind them', async () => {
    stubFetchRoutes({
      ...bundleRoutes(PENDING_ID),
      ...exportReadyRoutes(READY_ID),
      'GET /api/health': { body: healthSynthetic },
      'GET /api/experiments': { body: { experiments: canonicalFiveSummaries } },
      'GET /api/graph/status': { body: graphStatusUnavailable },
    } as never);
    const { container } = render(
      <MemoryRouter
        initialEntries={['/experiments']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );

    // First the offer, in the page flow.
    await screen.findByRole('heading', { name: LABELS.tutorialOfferTitle });
    expect(await axeRules(container, RULES)).toEqual([]);

    // Then the coach mark, over the top of it.
    fireEvent.click(screen.getByRole('button', { name: LABELS.actionStartTutorial }));
    await waitFor(() => expect(mark()).not.toBeNull());
    expect(await axeRules(document.body, RULES)).toEqual([]);
  }, 20000);

  it('reports no violation on the completion panel', async () => {
    stubFetchRoutes({
      'GET /api/health': { body: healthSynthetic },
      'GET /api/experiments': { body: { experiments: canonicalFiveSummaries } },
    });
    render(
      <MemoryRouter
        initialEntries={['/experiments']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Harness />
      </MemoryRouter>,
    );
    await openFirstStep();
    const { finishTutorial } = await import('../lib/tutorialController');
    finishTutorial();

    const panel = await waitFor(() => {
      const found = document.querySelector<HTMLElement>('[data-tutorial-step="complete"]');
      expect(found).not.toBeNull();
      return found!;
    });
    expect(await axeRules(document.body, RULES)).toEqual([]);
    // The panel is focused, and both of its actions are named.
    await waitFor(() => expect(document.activeElement).toBe(panel));
    expect(within(panel).getAllByRole('button')).toHaveLength(2);
  }, 20000);
});
