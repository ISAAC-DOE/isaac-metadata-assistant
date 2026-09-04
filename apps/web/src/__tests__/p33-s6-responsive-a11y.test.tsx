/*
 * P33 S6 (RESP-1 / D11 / D12 + residual cleanup) — deterministic contract.
 *
 * What jsdom CAN verify (and does here):
 *  - the AssistantDrawer's dialog behaviour: the trigger toggles it, aria-expanded
 *    tracks state, focus is trapped, Escape closes and restores focus to the
 *    trigger, and the in-panel Close button closes it too;
 *  - M1: the Guided Completion backend-down branch exposes exactly one <h1>;
 *  - M2: the Help trigger's icon is aria-hidden while the button keeps its name;
 *  - the dead-CSS removal (rules absent from the stylesheet source);
 *  - D12: a workspace search row shows its owning experiment when that adds
 *    information beyond the field label, and omits it when it would be redundant.
 *
 * What jsdom CANNOT verify (explicitly out of scope here): the media-query-driven
 * NARROW LAYOUT itself. jsdom applies no CSS and its viewport is fixed, so the
 * "rail collapses / panes stack / panels go fluid" behaviour is human-QA + live
 * CSSOM (the orchestrator confirms the max-width media queries exist on the
 * deployed build). The drawer's *behaviour* is viewport-independent by design, so
 * it is fully testable above even though its narrow *presentation* is not.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AssistantDrawer } from '../components/AssistantDrawer';
import { HelpPanel } from '../components/HelpPanel';
import { TopBar } from '../components/TopBar';
import { AppRoutes } from '../App';
import { stubFetchDown, stubFetchRoutes, searchResponse, searchRoutes } from '../test/apiFixtures';

// CSS source is pulled in as raw strings via Vite's import.meta.glob (the same
// pattern as no-vertical-rail.test.ts), so no node:fs / @types/node is needed.
const cssFiles = import.meta.glob(['../components/evidence.css', '../components/fields.css'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;
const cssByName = (name: string): string =>
  Object.entries(cssFiles).find(([path]) => path.endsWith(name))?.[1] ?? '';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RESP-1 · AssistantDrawer — dialog behaviour (viewport-independent)', () => {
  // The drawer trigger / close are CSS-hidden on desktop and only revealed by
  // max-width media queries; jsdom applies that base CSS (display:none), which
  // also empties their computed accessible name. So the two CSS-hidden controls
  // are reached by class (their labelling is asserted via textContent/aria-label),
  // while the OPEN panel — which carries no display:none — is reached by its ARIA
  // role + aria-label name like any dialog. This isolates the drawer's BEHAVIOUR
  // (viewport-independent) from its narrow PRESENTATION (not testable in jsdom,
  // which renders no layout).
  function renderDrawer(label?: string) {
    const view = render(
      <AssistantDrawer railClassName="record-right narrow" label={label}>
        <button type="button">inner-one</button>
        <button type="button">inner-two</button>
      </AssistantDrawer>,
    );
    const trigger = view.container.querySelector('.assistant-drawer-trigger') as HTMLButtonElement;
    const close = () => view.container.querySelector('.assistant-drawer-close') as HTMLButtonElement;
    return { view, trigger, close };
  }

  it('is closed initially: a labelled trigger, aria-expanded=false, no dialog', () => {
    const { view, trigger } = renderDrawer();
    expect(trigger).not.toBeNull();
    expect(trigger.textContent).toContain('Assistant'); // clearly labelled
    expect(trigger.getAttribute('aria-haspopup')).toBe('dialog');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(view.queryByRole('dialog', { hidden: true })).toBeNull();
  });

  it('the trigger toggles the drawer and flips aria-expanded', () => {
    const { view, trigger } = renderDrawer();
    fireEvent.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(view.getByRole('dialog', { name: 'Assistant' })).toBeTruthy();
    fireEvent.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(view.queryByRole('dialog', { hidden: true })).toBeNull();
  });

  it('opening moves focus into the panel and marks it aria-modal', () => {
    const { view, trigger } = renderDrawer();
    fireEvent.click(trigger);
    const dialog = view.getByRole('dialog', { name: 'Assistant' });
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(document.activeElement).toBe(dialog);
  });

  it('traps Tab within the panel (wraps at the boundary) — and focus actually MOVES between two distinct controls', () => {
    /*
     * C-1 (independent review, 2026-09-03) — CONTAINMENT ALONE IS NOT PROOF
     * OF A WORKING TRAP. `dialog.contains(document.activeElement)` stays
     * true even if focus never moved at all — e.g. `next.focus()` called on
     * an item CSS actually hides is a no-op, so `document.activeElement`
     * stays on whatever it already was — which is STILL "contained" by the
     * dialog. That is precisely how six sequential Tab presses from the
     * close button, measured live in a real browser, never left it: this
     * assertion style would have passed the whole time.
     *
     * N-1 (re-review, 2026-09-03) — NAMING THE ACTUAL FIX, NOT A DISCARDED
     * ONE. An earlier revision of this comment named
     * `getClientRects().length > 0` as the mechanism. That was tried and
     * abandoned before this file was last touched: jsdom has no layout
     * engine, so EVERY element's `getClientRects()` is empty there
     * regardless of its CSS, which would have collapsed the trap's item
     * list to zero and broken every test below. The code in
     * `AssistantDrawer.tsx` uses `getComputedStyle(...).display`/
     * `visibility`, walked from each candidate up to the panel
     * (ancestor-aware, since `display` is not inherited — a button inside a
     * `display: none` wrapper reports its OWN `inline-block`, not `none`).
     *
     * AND STATED PLAINLY RATHER THAN IMPLIED: THIS TEST DOES NOT DETECT THAT
     * MUTANT. Measured directly — removing the visibility filter from
     * `AssistantDrawer.tsx` entirely and re-running this file still passes
     * 26/26, because `renderDrawer()`'s fixture holds only two plain,
     * always-visible `<button>`s beside the real component's own controls,
     * and (separately measured) jsdom's `.focus()` does not appear to
     * respect `display: none` the way a real browser's does — calling it on
     * a hidden element still moves `document.activeElement` here. So the
     * "focus MOVED, not merely contained" assertions below hardens this
     * test against a DIFFERENT, weaker class of regression (a trap that
     * literally never advances focus at all) but cannot stand in for the
     * real guarantee. The C-1 guarantee — that a CSS-hidden control is
     * excluded from the cycle and Tab actually reaches the composer — is
     * proven ONLY in a real browser, in `e2e/specs/keyboard.spec.ts`
     * (`@interaction the assistant drawer trap moves focus to the composer
     * at 768px`), and that spec is the one to trust for this property.
     */
    const { view, trigger } = renderDrawer();
    fireEvent.click(trigger);
    const dialog = view.getByRole('dialog');
    const before = document.activeElement;
    expect(fireEvent.keyDown(dialog, { key: 'Tab' })).toBe(false);
    const afterOne = document.activeElement;
    expect(dialog.contains(afterOne)).toBe(true);
    expect(afterOne).not.toBe(before); // focus MOVED, not merely "still inside"

    expect(fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true })).toBe(false);
    const afterTwo = document.activeElement;
    expect(dialog.contains(afterTwo)).toBe(true);
    expect(afterTwo).not.toBe(afterOne); // Shift+Tab moved it again, elsewhere
  });

  /*
   * N-2 (re-review, 2026-09-03) — A BUTTON INSIDE A `display: none` WRAPPER
   * IS SKIPPED, NOT MERELY A `display: none` ELEMENT ITSELF.
   *
   * `display` is not inherited: a real, enabled `<button>` nested inside a
   * hidden ancestor still reports its OWN computed `display` as (say)
   * `inline-block`, never `none` — so a filter that reads only the
   * candidate's own computed style would let it straight through, then
   * `.focus()` on it is a no-op in a real browser, exactly the C-1 shape of
   * bug one level removed. `AssistantDrawer.tsx`'s `isReachableFocusTarget`
   * walks the candidate's OWN ancestor chain up to the panel to catch this.
   *
   * This IS a mutation this jsdom test can detect (unlike C-1's main
   * defect): jsdom computes `display: none` correctly from inline styles
   * regardless of layout, so a per-element-only check really does let
   * `hidden-inner` through here, and the ancestor walk really does exclude
   * it — verified by literally reverting `isReachableFocusTarget` to check
   * only `el` itself (dropping the ancestor loop) and re-running this test:
   * it fails, naming `hidden-inner` as reached.
   */
  it('a focusable control nested inside a display:none WRAPPER is excluded from the trap (ancestor-aware)', () => {
    const view = render(
      <AssistantDrawer railClassName="record-right narrow">
        <button type="button">reachable-one</button>
        <div style={{ display: 'none' }}>
          <button type="button">hidden-inner</button>
        </div>
        <button type="button">reachable-two</button>
      </AssistantDrawer>,
    );
    const trigger = view.container.querySelector('.assistant-drawer-trigger') as HTMLButtonElement;
    fireEvent.click(trigger);
    const dialog = view.getByRole('dialog');

    const seen = new Set<string>();
    let node: Element | null = document.activeElement;
    if (node) seen.add(node.textContent ?? '<none>');
    // Walk enough Tab presses to cycle the whole (short) list at least twice
    // over, so a wraparound would surface `hidden-inner` if it were in the
    // cycle at all.
    for (let i = 0; i < 8; i++) {
      fireEvent.keyDown(dialog, { key: 'Tab' });
      node = document.activeElement;
      seen.add(node?.textContent ?? '<none>');
    }

    expect(seen.has('hidden-inner')).toBe(false);
    expect(seen.has('reachable-one')).toBe(true);
    expect(seen.has('reachable-two')).toBe(true);
  });

  it('Shift+Tab from the just-opened panel lands on the LAST focusable (MIN-2)', () => {
    const { view, trigger } = renderDrawer();
    fireEvent.click(trigger);
    const dialog = view.getByRole('dialog');
    // Focus is on the panel itself right after open (not in the focusable list).
    expect(document.activeElement).toBe(dialog);
    // Shift+Tab must wrap to the LAST focusable — the last inner button — not the
    // second-to-last (the old `(idx + delta) % n` math with idx = -1).
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(view.getByText('inner-two'));
  });

  it('Escape closes the drawer and restores focus to the trigger', () => {
    const { view, trigger } = renderDrawer();
    trigger.focus();
    fireEvent.click(trigger);
    expect(view.getByRole('dialog')).toBeTruthy();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(view.queryByRole('dialog', { hidden: true })).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('the in-panel Close button closes the drawer and restores focus', () => {
    const { view, trigger, close } = renderDrawer();
    trigger.focus();
    fireEvent.click(trigger);
    const closeBtn = close();
    expect(closeBtn.getAttribute('aria-label')).toBe('Close assistant'); // labelled
    fireEvent.click(closeBtn);
    expect(view.queryByRole('dialog', { hidden: true })).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('honours a custom accessible label (Project Memory rail)', () => {
    const { view, trigger } = renderDrawer('Assistant (advisory)');
    expect(trigger.textContent).toContain('Assistant (advisory)');
    fireEvent.click(trigger);
    expect(view.getByRole('dialog', { name: 'Assistant (advisory)' })).toBeTruthy();
  });
});

describe('MIN-3 · resizing to desktop force-closes the drawer (state hygiene)', () => {
  it('a narrow→wide crossing sets open=false so desktop never carries dialog semantics', () => {
    // jsdom has no matchMedia; install a controllable mock we can flip + fire.
    let listeners: Array<() => void> = [];
    const mql = {
      matches: false, // start "narrow" (min-width:1024 not yet matched)
      media: '(min-width: 1024px)',
      addEventListener: (_t: string, cb: () => void) => listeners.push(cb),
      removeEventListener: (_t: string, cb: () => void) => {
        listeners = listeners.filter((l) => l !== cb);
      },
    };
    vi.stubGlobal('matchMedia', () => mql);

    const view = render(
      <AssistantDrawer railClassName="record-right narrow">
        <button type="button">inner</button>
      </AssistantDrawer>,
    );
    const trigger = view.container.querySelector('.assistant-drawer-trigger') as HTMLButtonElement;

    // Open it at narrow width.
    fireEvent.click(trigger);
    expect(view.getByRole('dialog')).toBeTruthy();
    expect(trigger.getAttribute('aria-expanded')).toBe('true');

    // Cross to desktop: the media query now matches → fire the change listener
    // (wrapped in act so the resulting state update flushes before we assert).
    act(() => {
      mql.matches = true;
      listeners.forEach((cb) => cb());
    });

    // The slide-over/dialog semantics are gone on desktop.
    expect(view.queryByRole('dialog', { hidden: true })).toBeNull();
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  });
});

describe('M1 · Guided Completion backend-down branch has exactly one h1', () => {
  it('renders one screen-level h1 even when the backend is unreachable', async () => {
    stubFetchDown();
    const view = render(
      <MemoryRouter
        initialEntries={['/record/demo/complete']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AppRoutes />
      </MemoryRouter>,
    );
    // Wait for the backend-down state to render (unique title).
    await view.findByText('Backend Not Running');
    expect(view.container.querySelectorAll('h1')).toHaveLength(1);
  });
});

describe('M2 · Help trigger icon is aria-hidden, button keeps its name', () => {
  it('names the button "Help" and hides its decorative icon from AT', () => {
    const view = render(<HelpPanel />);
    const trigger = view.getByRole('button', { name: 'Help' });
    const svg = trigger.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg!.getAttribute('aria-hidden')).toBe('true');
  });
});

describe('Cleanup · orphaned CSS rules are removed', () => {
  it('evidence.css no longer defines .ev-panel-* or .ev-field', () => {
    const css = cssByName('evidence.css');
    expect(css.length).toBeGreaterThan(0);
    for (const selector of [
      '.ev-panel-card',
      '.ev-panel-head',
      '.ev-panel-title',
      '.ev-panel-badge',
      '.ev-panel-for',
      '.ev-field',
    ]) {
      expect(css.includes(selector)).toBe(false);
    }
  });

  it('fields.css no longer defines the now-dead .field-row.selectable / .selected', () => {
    const css = cssByName('fields.css');
    expect(css.length).toBeGreaterThan(0);
    // The TSX plumbing that applied these was removed, so the rules are dead.
    expect(css.includes('.field-row.selectable')).toBe(false);
    expect(css.includes('.field-row.selected')).toBe(false);
  });
});

describe('D12 · workspace search rows disambiguate by owning experiment', () => {
  function renderTopBar() {
    return render(
      <MemoryRouter
        initialEntries={['/experiments']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <TopBar variant="home" />
      </MemoryRouter>,
    );
  }

  async function openAndType(view: ReturnType<typeof renderTopBar>, query = 'beamline') {
    fireEvent.click(view.getByRole('button', { name: /search/i }));
    const dialog = await view.findByRole('dialog');
    fireEvent.change(within(dialog).getByRole('searchbox'), { target: { value: query } });
    return dialog;
  }

  it('shows the owning experiment when the field label alone is ambiguous', async () => {
    // A draft_field match whose label ("Beamline") differs from the owning
    // experiment title — exactly the duplicate-label case D12 disambiguates.
    const body = {
      ...searchResponse,
      workspace: {
        ...searchResponse.workspace,
        results: [
          {
            ...searchResponse.workspace.results[0],
            kind: 'draft_field' as const,
            label: 'Beamline',
            title: 'Synthetic XANES — CuO (Cu K-edge) Demo',
            match: {
              field: 'draft.measurement.beamline.value',
              snippet: 'BL-7',
              reason: 'matched draft field value',
              tier: 'substring' as const,
              offsets: [] as [number, number][],
            },
          },
        ],
      },
    };
    stubFetchRoutes(searchRoutes({ query: 'beamline', body }));
    const view = renderTopBar();
    const dialog = await openAndType(view);
    expect(await within(dialog).findByText('Beamline')).toBeTruthy();
    expect(within(dialog).getByText(/Synthetic XANES — CuO \(Cu K-edge\) Demo/)).toBeTruthy();
  });

  it('omits the context when it would merely repeat the label (experiment hit)', async () => {
    // The default fixture is an `experiment` hit whose label === title: showing
    // "in <title>" would be redundant, so no context line is rendered.
    stubFetchRoutes(searchRoutes({ query: 'xanes' }));
    const view = renderTopBar();
    const dialog = await openAndType(view, 'xanes');
    await within(dialog).findByText(searchResponse.workspace.results[0].label);
    expect(dialog.querySelector('.search-result-context')).toBeNull();
  });
});
