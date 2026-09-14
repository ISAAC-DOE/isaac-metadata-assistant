/**
 * PR-E — the desktop Assistant rail collapse/expand toggle
 * (`components/AssistantDrawer.tsx`).
 *
 * HONESTY ABOUT WHAT IS PROVEN HERE, following `assistant-shell-layout.test.tsx`'s
 * own convention: nothing here measures a rendered pixel, a rail width, or
 * whether content is VISUALLY hidden at a given viewport. Every assertion
 * below is RENDERED — real DOM structure, attributes, persisted storage, and
 * focus — which is exactly what the mutation controls this slice's brief asks
 * for need: proof that collapsing/expanding never unmounts the panel or
 * resets state, not a pixel measurement (that is the PR report's
 * browser-measured job).
 *
 * THE TOGGLE IS FOUND BY `container.querySelector`, NOT `getByRole`, matching
 * this repository's own established pattern for the mobile drawer trigger
 * (`p33-s6-responsive-a11y.test.tsx`). Reason, measured directly: this
 * project's `vite.config.ts` sets `test: { css: true }`, so real stylesheets
 * ARE parsed in jsdom — but jsdom's default test viewport is exactly
 * `1024×768` and its CSS engine does not evaluate `@media` conditions the way
 * a real browser does, so a control that is only unhidden inside a
 * `(min-width: 1025px)` (or `max-width: 1024px`) block never becomes
 * "accessible" by `getByRole`'s hidden-element filtering in this test
 * environment, even though it renders correctly in every real browser this
 * slice measured (see the PR report). `querySelector` sidesteps that
 * environment quirk entirely, exactly as the pre-existing drawer-trigger
 * tests already do.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { renderToStaticMarkup } from 'react-dom/server';
import { AssistantDrawer } from '../components/AssistantDrawer';
import { AssistantPanel } from '../components/AssistantPanel';
import { clearAllSessions } from '../lib/assistantSession';
import type { AssistantMessage } from '../lib/types';

/**
 * `reply` is a REQUIRED prop of `AssistantPanel`, so the UX-022 cases below
 * that render the real panel have to supply one. A properly typed constant
 * rather than an inline literal or a cast: the empty-text resting message is
 * exactly what `assistant-workspace-context.test.tsx` uses for the same
 * purpose, so the two harnesses cannot drift, and `AssistantMessage` is
 * checked by `tsc` rather than asserted away.
 *
 * `vitest` type-checks nothing, which is how the first version of this
 * harness ran green here while failing CI's separate Build step.
 */
const RESTING_REPLY: AssistantMessage = { text: '', answeredFrom: 'workflow' };

const STORAGE_KEY = 'isaac.assistant-rail-collapsed';

/** A tiny stand-in for AssistantPanel that carries state a real collapse must
 *  never disturb: an uncontrolled textarea, like the real composer. */
function FakeAssistantPanelContent() {
  return (
    <div className="assistant">
      <div className="assistant-head">
        <div className="assistant-head-titles">
          <span className="assistant-label" tabIndex={-1}>
            Assistant
          </span>
        </div>
      </div>
      <textarea aria-label="Ask the assistant a question" defaultValue="" />
    </div>
  );
}

function getToggle(container: HTMLElement): HTMLButtonElement {
  const el = container.querySelector('button.assistant-rail-toggle');
  if (!el) throw new Error('assistant-rail-toggle not found');
  return el as HTMLButtonElement;
}

function toggleLabel(container: HTMLElement): string {
  return getToggle(container).querySelector('.assistant-rail-toggle-label')?.textContent ?? '';
}

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  window.localStorage.clear();
});

describe('PR-E · AssistantDrawer desktop rail collapse', () => {
  /*
   * UX-013 — THIS TEST IS INVERTED, NOT NEW, AND NOT DELETED. Its previous
   * title was "renders one toggle button, OPEN by default" and it asserted
   * `aria-expanded="true"` / `data-collapsed="false"` / "Collapse Assistant".
   * It passed, and it was pinning the defect: the scope directive requires the
   * Assistant to stay contextual and collapsed rather than permanently consume
   * the scientist's working width. Inverting a test that pins a defect — rather
   * than deleting it — is this repository's established remedy, because the
   * inverted assertion still fails if the default silently flips back.
   */
  it('renders one toggle button, COLLAPSED by default, with aria-expanded/aria-controls', () => {
    const { container } = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    const toggle = getToggle(container);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    const aside = container.querySelector('aside.assistant-drawer-panel')!;
    // M-1 (independent review, 2026-09-03) — `aria-controls` names the
    // element this button actually shows/hides, `.assistant-drawer-content`,
    // NOT the whole `<aside>` (that id is what the ≤1024px trigger's OWN
    // `aria-controls` correctly points to, since it opens/closes the entire
    // dialog).
    const content = container.querySelector('.assistant-drawer-content')!;
    expect(toggle.getAttribute('aria-controls')).toBe(content.id);
    expect(content.id).not.toBe(aside.id);
    expect(aside.getAttribute('data-collapsed')).toBe('true');
    expect(toggleLabel(container)).toBe('Expand Assistant');
  });

  it('clicking the toggle flips aria-expanded, data-collapsed, and the visible/accessible label — which states the RESULTING action', () => {
    const { container } = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    const toggle = getToggle(container);
    const aside = container.querySelector('aside.assistant-drawer-panel')!;

    // UX-013 — the two arms are SWAPPED relative to the pre-UX-013 version of
    // this test, because the starting state is now collapsed. The round trip
    // itself is what is under test and it is unchanged.
    fireEvent.click(toggle); // expand
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(aside.getAttribute('data-collapsed')).toBe('false');
    expect(toggleLabel(container)).toBe('Collapse Assistant');

    fireEvent.click(toggle); // collapse
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(aside.getAttribute('data-collapsed')).toBe('true');
    expect(toggleLabel(container)).toBe('Expand Assistant');
  });

  it("MUTATION CONTROL 1 — collapsing/expanding never unmounts the panel: a typed composer value survives the round trip", () => {
    const { container, getByLabelText } = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    const textarea = getByLabelText('Ask the assistant a question') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'What is blocking export?' } });
    expect(textarea.value).toBe('What is blocking export?');

    const toggle = getToggle(container);
    fireEvent.click(toggle); // expand   (UX-013: the default is now collapsed)
    fireEvent.click(toggle); // collapse

    const sameTextarea = getByLabelText('Ask the assistant a question') as HTMLTextAreaElement;
    expect(sameTextarea).toBe(textarea); // same DOM node — never remounted
    expect(sameTextarea.value).toBe('What is blocking export?');
  });

  it("MUTATION CONTROL 2 — the content is a single mount for the drawer's lifetime: the panel's own DOM node keeps its identity across a collapse cycle (an unmount+remount would create a NEW node)", () => {
    const { container } = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    const panelBefore = container.querySelector('.assistant-drawer-content .assistant');
    expect(panelBefore).not.toBeNull();

    const toggle = getToggle(container);
    fireEvent.click(toggle); // expand   (UX-013: the default is now collapsed)
    fireEvent.click(toggle); // collapse

    const panelAfter = container.querySelector('.assistant-drawer-content .assistant');
    // Same object reference — proves the element was never torn down and
    // recreated, not merely that a NEW element happens to carry the same
    // class name.
    expect(panelAfter).toBe(panelBefore);
  });

  it('MUTATION CONTROL 3 — main-column content beside the drawer is untouched by a collapse: an unrelated sibling input keeps its value', () => {
    function Harness() {
      return (
        <div>
          <input aria-label="main column note" defaultValue="" />
          <AssistantDrawer railClassName="record-right narrow">
            <FakeAssistantPanelContent />
          </AssistantDrawer>
        </div>
      );
    }
    const { container, getByLabelText } = render(<Harness />);
    const mainInput = getByLabelText('main column note') as HTMLInputElement;
    fireEvent.change(mainInput, { target: { value: 'unsaved draft text' } });

    fireEvent.click(getToggle(container));

    expect((getByLabelText('main column note') as HTMLInputElement).value).toBe(
      'unsaved draft text',
    );
  });

  it('persists the preference across mounts (localStorage), and hydrates it on the NEXT mount rather than the first paint', async () => {
    const first = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    // UX-013 — default: COLLAPSED, nothing stored yet. The click therefore
    // EXPANDS and persists `'0'`, which is the case that matters most: the
    // stored-preference effect is what makes "a scientist who expands it once
    // keeps it expanded" true, so this test is the one that would catch a
    // default flip implemented by deleting the effect instead of inverting the
    // reader.
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
    fireEvent.click(getToggle(first.container));
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('0');
    first.unmount();

    const second = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    // Hydrated from storage after mount (an effect, not the first render) —
    // the eventual state is EXPANDED, which is the opposite of the default this
    // mount rendered first.
    await waitFor(() => {
      expect(toggleLabel(second.container)).toBe('Collapse Assistant');
    });
  });

  /*
   * UX-013 — INVERTED for the same reason as the default-state test above, and
   * the inversion here closed a second, smaller hole. Before UX-013 this
   * function's `catch` returned `false` while the default was also `false`, so
   * the two agreed by accident. Had the default been flipped without touching
   * the `catch`, a storage-refusing browser would have become the ONE
   * environment where the rail still opened by default — a divergence no test
   * asserted in either direction. It is asserted now.
   *
   * *** AND THE INVERSION EXPOSED THAT THIS TEST HAD NEVER INJECTED ANYTHING.
   * Measured while mutation-testing the flip: assigning
   * `window.localStorage.getItem = fn` is SILENTLY IGNORED by this jsdom — the
   * own-property assignment does not shadow `Storage.prototype.getItem`, so the
   * replacement function was never called and the `catch` branch was never
   * entered. A probe confirmed it directly (`MOCK_CALLED=false THREW=false`),
   * and `vi.spyOn(Storage.prototype, 'getItem')` confirmed the working form
   * (`PROTO_THREW=true`).
   *
   * The mutation that proved it: changing the `catch` to `return false`
   * survived the whole file — 16 passed — with the mutation ASSERTED to have
   * applied. So this test read as fault-injection coverage while injecting no
   * fault, in BOTH polarities, since it was written. The same was true of the
   * write-side test below, whose `not.toThrow()` passed against a `setItem`
   * that never threw. Both now spy on the PROTOTYPE and both ASSERT the spy was
   * called — because a fault that was never injected is not a fault that was
   * tolerated. ***
   */
  it('a browser that refuses storage still works: the rail defaults COLLAPSED and the toggle still functions', () => {
    // THE INJECTION IS ON `Storage.prototype`, NOT ON THE INSTANCE, and that
    // correction is the reason this test now means anything — see the block
    // comment above.
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage disabled');
    });
    try {
      const { container } = render(
        <AssistantDrawer railClassName="record-right narrow">
          <FakeAssistantPanelContent />
        </AssistantDrawer>,
      );
      // Proof the fault was actually injected, asserted rather than assumed: a
      // read that never happens cannot be a read that was refused.
      expect(spy).toHaveBeenCalled();
      expect(toggleLabel(container)).toBe('Expand Assistant');
      spy.mockRestore();
      fireEvent.click(getToggle(container));
      expect(toggleLabel(container)).toBe('Collapse Assistant');
    } finally {
      spy.mockRestore();
    }
  });

  /*
   * M-3 (independent review, 2026-09-03) — the WRITE side, mocked
   * separately from the READ side above. `readStoredRailCollapsed` and
   * `writeStoredRailCollapsed` are two different functions with two
   * different try/catch blocks; the test above proves only the read one.
   * Removing `writeStoredRailCollapsed`'s try/catch is the mutation this
   * guards: `window.localStorage.setItem` would throw synchronously inside
   * the button's `onClick` handler, and with no try/catch that throw
   * propagates out of the React event handler — this test fails loudly
   * (an unhandled error) rather than silently passing if that guard is
   * removed.
   */
  it('a browser that refuses to WRITE storage still works: toggling neither crashes nor throws', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage disabled (write)');
    });
    try {
      const { container } = render(
        <AssistantDrawer railClassName="record-right narrow">
          <FakeAssistantPanelContent />
        </AssistantDrawer>,
      );
      expect(() => fireEvent.click(getToggle(container))).not.toThrow();
      // The in-memory state still updates even though persistence failed —
      // the failure is contained to storage, not to the feature. (UX-013: the
      // arms are swapped, because the first click now expands.)
      expect(toggleLabel(container)).toBe('Collapse Assistant');
      expect(() => fireEvent.click(getToggle(container))).not.toThrow();
      expect(toggleLabel(container)).toBe('Expand Assistant');
      // Proof the fault was injected. Before this correction the assertion
      // above was `not.toThrow()` against a `setItem` that never threw, so it
      // could not distinguish a contained failure from no failure at all.
      expect(spy).toHaveBeenCalled();
    } finally {
      spy.mockRestore();
    }
  });

  it('expanding moves focus to the panel heading; collapsing leaves focus on the same control', async () => {
    const { container } = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    const toggle = getToggle(container);
    toggle.focus();

    // UX-013 — the arms are swapped because the default is now collapsed, and
    // the ORDER matters for what this proves. Expanding first means the focus
    // move is asserted from the state a reader actually starts in, rather than
    // from a state only reachable by clicking twice.
    fireEvent.click(toggle); // expand — focus moves to the panel heading
    await waitFor(() => {
      expect(document.activeElement?.className).toContain('assistant-label');
    });

    getToggle(container).focus();
    fireEvent.click(getToggle(container)); // collapse — focus stays on this control
    expect(document.activeElement).toBe(getToggle(container));
  });

  /*
   * UX-013 — THE THREE-WAY STORAGE DISTINCTION, which is the new load-bearing
   * logic and had no test in either polarity before this slice.
   *
   * `readStoredRailCollapsed` now has to keep three cases apart, and only ONE
   * of them means expanded. The obvious wrong implementation of a "default
   * collapsed" flip is `useState(true)` with the reader left at `=== '1'`: that
   * renders collapsed, passes every test above, and QUIETLY DESTROYS the stored
   * preference — a scientist who expands the rail gets `'0'` written, the next
   * mount reads `'0' === '1'` as `false`, and... happens to work. The mutant
   * that actually survives the tests above is the one that leaves the reader at
   * `=== '1'` while the WRITE side changes, or that returns `false` from the
   * `catch`. So each case is asserted on its own, by seeding storage directly
   * rather than by clicking, because clicking can only ever produce the two
   * values the writer already agrees about.
   */
  it.each([
    ['absent (a reader who has never touched the toggle)', null, 'Expand Assistant'],
    ["explicitly collapsed ('1')", '1', 'Expand Assistant'],
    ["explicitly EXPANDED ('0') — the preference that must survive", '0', 'Collapse Assistant'],
    ['an unrecognised value falls on the DEFAULT side', 'yes', 'Expand Assistant'],
  ])('hydrates from stored state: %s', async (_label, stored, expectedLabel) => {
    if (stored !== null) window.localStorage.setItem(STORAGE_KEY, stored);
    const { container } = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    await waitFor(() => {
      expect(toggleLabel(container)).toBe(expectedLabel);
    });
  });

  it('MUTATION-GUARDED — reading the preference NEVER writes it, so merely mounting cannot convert an absent preference into a stored one', () => {
    // Without this, a reader implemented as "normalise the stored value on
    // mount" would write `'1'` for every first-time reader, making the default
    // indistinguishable from an explicit choice forever after — and no
    // assertion above would notice, because the rendered result is identical.
    const { unmount } = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
    unmount();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  /*
   * UX-013 — THE FIRST PAINT, and the reason this test uses a SERVER render.
   *
   * `useState(true)` vs `useState(false)` is an EQUIVALENT MUTANT under every
   * other test in this file, and that is a property of the harness rather than
   * of the code: `render()` from testing-library wraps in `act()`, which
   * flushes the passive effect that reads storage, so by the time any assertion
   * runs the state is whatever the EFFECT decided. Measured — flipping the
   * initial literal to `false` left all 16 tests green.
   *
   * The difference the initial literal actually makes is the one frame before
   * that effect runs, which is exactly what the component's own comment claims
   * ("the first paint still does not depend on storage"). `renderToStaticMarkup`
   * runs NO effects, so it observes that frame directly and nothing else can.
   *
   * Storage is seeded with the OPPOSITE preference on purpose. If the first
   * paint consulted storage — the change this test exists to forbid — the
   * markup would come back expanded, and a reader on a slow hydration would
   * briefly see the rail cover the column they are working in.
   */
  it('MUTATION-GUARDED — the FIRST paint is collapsed and does not consult storage', () => {
    window.localStorage.setItem(STORAGE_KEY, '0'); // stored preference: EXPANDED
    const markup = renderToStaticMarkup(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    expect(markup).toContain('data-collapsed="true"');
    expect(markup).not.toContain('data-collapsed="false"');
    // Positive control: this assertion is only meaningful because the attribute
    // is present at all in server markup. Without it, a renderer that emitted
    // no `data-collapsed` would satisfy both assertions above.
    expect(markup).toMatch(/data-collapsed="(true|false)"/);
  });

  it('the toggle is a real, enabled button (in the tab order)', () => {
    const { container } = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    const toggle = getToggle(container);
    expect(toggle.tagName).toBe('BUTTON');
    expect(toggle.disabled).toBe(false);
    expect(toggle.getAttribute('type')).toBe('button');
    expect(toggle.tabIndex).toBeGreaterThanOrEqual(0);
  });

  it('the content wrapper stays mounted and CONTAINS the panel in every collapse state', () => {
    const { container } = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    const contentWrapper = container.querySelector('.assistant-drawer-content')!;
    expect(contentWrapper.querySelector('.assistant')).not.toBeNull();

    fireEvent.click(getToggle(container));
    // Still mounted (the hiding is CSS-only, via `display:none` scoped to the
    // desktop-collapsed band — see assistant-drawer.css); this test does not
    // and cannot assert the CSS itself (no layout engine here), only that the
    // DOM was never removed.
    expect(container.querySelector('.assistant-drawer-content .assistant')).not.toBeNull();
  });
});

/* ══════════════════════════════════════════════════════════════════════════
 * UX-022 — THE TOGGLE RENDERS INSIDE THE PANEL'S OWN HEADER WHEN EXPANDED
 *
 * Every case above renders a child that publishes no header slot, so every
 * case above exercises the INLINE arm — which is the arm the collapsed rail
 * needs and which must never change. This block exercises the other arm, with
 * the REAL `AssistantPanel` rather than a stand-in, because the whole point is
 * that two files agree about one contract: `AssistantPanel` publishes a slot
 * through `AssistantRailToggleSlotContext` and `AssistantDrawer` portals its
 * one button into it.
 *
 * WHAT THIS EXISTS TO CATCH. The owner reported the assistant's header as
 * cluttered; measured in real Chromium at 1280x800 on the 308px record rail,
 * `button.assistant-rail-toggle` was a 24.3px strip at y=93 sitting OUTSIDE
 * `section.assistant` (y=123.3), so the panel's own title was not the panel's
 * first element. The naive repair — render the button inside the header —
 * breaks the feature outright, because the header lives inside
 * `.assistant-drawer-content`, which `assistant-drawer.css` hides with
 * `display: none` in the desktop-collapsed band. That is the DEFAULT state, so
 * a rail collapsed on first load would have no visible control in it and could
 * never be re-opened. Hence: ONE button, two positions, asserted here in both.
 *
 * FOCUS IS ASSERTED HERE AND NOT IN A BROWSER, DELIBERATELY. The collapse
 * moves the button between the portal and the inline position, which React
 * commits as an unmount + mount, so focus needs re-asserting. It could not be
 * measured in the Chromium this change was otherwise measured in: a
 * browser-automation tab reports `document.hasFocus() === false` and
 * `visibilityState: "hidden"`, and `document.activeElement` reads `<body>`
 * there even on the pre-existing EXPAND path, which is unchanged code. A
 * non-answer is not a measurement; jsdom can answer it, so jsdom does.
 * ══════════════════════════════════════════════════════════════════════════ */
describe('UX-022 · the collapse toggle is a header item when the rail is open', () => {
  afterEach(() => {
    cleanup();
    clearAllSessions();
  });

  const drawerWithRealPanel = () =>
    render(
      <AssistantDrawer railClassName="record-right narrow">
        <AssistantPanel
          reply={RESTING_REPLY}
          prompts={[]}
          experimentId="ux022"
          workspaceContext="Record Fields"
        />
      </AssistantDrawer>,
    );

  it('COLLAPSED (the default): exactly one toggle, and it is NOT inside the panel', () => {
    const { container } = drawerWithRealPanel();
    expect(container.querySelectorAll('button.assistant-rail-toggle').length).toBe(1);
    const toggle = getToggle(container);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(toggle.closest('.assistant-head')).toBeNull();
    // it is a child of the <aside>, i.e. OUTSIDE the content the collapsed band
    // hides — which is the only reason a collapsed rail can be re-opened at all
    expect(toggle.closest('.assistant-drawer-content')).toBeNull();
    expect(toggle.parentElement).toBe(container.querySelector('aside.assistant-drawer-panel'));
  });

  it('EXPANDED: still exactly one toggle, now the header\'s own item, with its contract intact', () => {
    const { container } = drawerWithRealPanel();
    fireEvent.click(getToggle(container));

    // ONE. A second copy would break `e2e/helpers/assistant.ts`, which selects
    // `button.assistant-rail-toggle` and reads its `aria-expanded`.
    expect(container.querySelectorAll('button.assistant-rail-toggle').length).toBe(1);
    const toggle = getToggle(container);
    const head = container.querySelector('.assistant-head') as HTMLElement;
    const slot = head.querySelector('.assistant-head-toggle') as HTMLElement;

    expect(toggle.closest('.assistant-head')).toBe(head);
    expect(toggle.parentElement).toBe(slot);
    // …and the panel's own name is now the panel's first element
    const section = container.querySelector('section.assistant') as HTMLElement;
    expect(section.firstElementChild).toBe(head);
    expect(head.querySelector('.assistant-label')!.textContent).toBe('Assistant');

    // THE CONTRACT SEVERAL SPECS DEPEND ON, unchanged by the move.
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(toggle.getAttribute('aria-controls')).toBe(
      container.querySelector('.assistant-drawer-content')!.id,
    );
    expect(toggleLabel(container)).toBe('Collapse Assistant');
    expect(toggle.getAttribute('aria-label')).toBeNull(); // visible text IS the name
    expect(toggle).not.toBeDisabled();
  });

  it('a full round trip keeps ONE toggle and returns focus to it — the portal remount does not drop focus', async () => {
    const { container } = drawerWithRealPanel();

    getToggle(container).focus();
    fireEvent.click(getToggle(container)); // expand
    await waitFor(() => {
      expect(document.activeElement?.className).toContain('assistant-label');
    });
    expect(container.querySelectorAll('button.assistant-rail-toggle').length).toBe(1);
    expect(getToggle(container).closest('.assistant-head')).not.toBeNull();

    getToggle(container).focus();
    fireEvent.click(getToggle(container)); // collapse — the button MOVES here
    expect(container.querySelectorAll('button.assistant-rail-toggle').length).toBe(1);
    expect(getToggle(container).closest('.assistant-head')).toBeNull();
    expect(toggleLabel(container)).toBe('Expand Assistant');
    /*
     * MUTATION-GUARDED. Without the `else` arm added to `handleRailToggle` this
     * assertion fails with `document.activeElement` on <body>: the node that
     * had focus was unmounted by the position change. Verified by removing that
     * arm and re-running.
     */
    await waitFor(() => {
      expect(document.activeElement).toBe(getToggle(container));
    });
  });

  it('collapsing/expanding still never unmounts the panel: a typed composer value survives the round trip', () => {
    const { container, getByLabelText } = drawerWithRealPanel();
    fireEvent.click(getToggle(container)); // expand

    const box = getByLabelText('Ask the assistant a question') as HTMLInputElement;
    fireEvent.change(box, { target: { value: 'half-typed question' } });

    fireEvent.click(getToggle(container)); // collapse
    fireEvent.click(getToggle(container)); // expand again
    expect(
      (getByLabelText('Ask the assistant a question') as HTMLInputElement).value,
    ).toBe('half-typed question');
    // and the SAME panel node survived — an unmount+remount would be a new node
    expect(container.querySelector('section.assistant')).not.toBeNull();
  });
});
