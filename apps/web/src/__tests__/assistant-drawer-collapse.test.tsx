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

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { AssistantDrawer } from '../components/AssistantDrawer';

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
  it('renders one toggle button, open by default, with aria-expanded/aria-controls', () => {
    const { container } = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    const toggle = getToggle(container);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    const aside = container.querySelector('aside.assistant-drawer-panel')!;
    // M-1 (independent review, 2026-09-03) — `aria-controls` names the
    // element this button actually shows/hides, `.assistant-drawer-content`,
    // NOT the whole `<aside>` (that id is what the ≤1024px trigger's OWN
    // `aria-controls` correctly points to, since it opens/closes the entire
    // dialog).
    const content = container.querySelector('.assistant-drawer-content')!;
    expect(toggle.getAttribute('aria-controls')).toBe(content.id);
    expect(content.id).not.toBe(aside.id);
    expect(aside.getAttribute('data-collapsed')).toBe('false');
    expect(toggleLabel(container)).toBe('Collapse Assistant');
  });

  it('clicking the toggle flips aria-expanded, data-collapsed, and the visible/accessible label — which states the RESULTING action', () => {
    const { container } = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    const toggle = getToggle(container);
    const aside = container.querySelector('aside.assistant-drawer-panel')!;

    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(aside.getAttribute('data-collapsed')).toBe('true');
    expect(toggleLabel(container)).toBe('Expand Assistant');

    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(aside.getAttribute('data-collapsed')).toBe('false');
    expect(toggleLabel(container)).toBe('Collapse Assistant');
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
    fireEvent.click(toggle); // collapse
    fireEvent.click(toggle); // expand

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
    fireEvent.click(toggle); // collapse
    fireEvent.click(toggle); // expand

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
    // Default: open, nothing stored yet.
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
    fireEvent.click(getToggle(first.container));
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('1');
    first.unmount();

    const second = render(
      <AssistantDrawer railClassName="record-right narrow">
        <FakeAssistantPanelContent />
      </AssistantDrawer>,
    );
    // Hydrated from storage after mount (an effect, not the first render) —
    // the eventual state is collapsed.
    await waitFor(() => {
      expect(toggleLabel(second.container)).toBe('Expand Assistant');
    });
  });

  it('a browser that refuses storage still works: the rail defaults open and the toggle still functions', () => {
    const original = window.localStorage.getItem;
    window.localStorage.getItem = () => {
      throw new Error('storage disabled');
    };
    try {
      const { container } = render(
        <AssistantDrawer railClassName="record-right narrow">
          <FakeAssistantPanelContent />
        </AssistantDrawer>,
      );
      expect(toggleLabel(container)).toBe('Collapse Assistant');
      fireEvent.click(getToggle(container));
      expect(toggleLabel(container)).toBe('Expand Assistant');
    } finally {
      window.localStorage.getItem = original;
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
    const original = window.localStorage.setItem;
    window.localStorage.setItem = () => {
      throw new Error('storage disabled (write)');
    };
    try {
      const { container } = render(
        <AssistantDrawer railClassName="record-right narrow">
          <FakeAssistantPanelContent />
        </AssistantDrawer>,
      );
      expect(() => fireEvent.click(getToggle(container))).not.toThrow();
      // The in-memory state still updates even though persistence failed —
      // the failure is contained to storage, not to the feature.
      expect(toggleLabel(container)).toBe('Expand Assistant');
      expect(() => fireEvent.click(getToggle(container))).not.toThrow();
      expect(toggleLabel(container)).toBe('Collapse Assistant');
    } finally {
      window.localStorage.setItem = original;
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
    fireEvent.click(toggle); // collapse — focus stays on this control (no code path moves it)
    expect(document.activeElement).toBe(toggle);

    fireEvent.click(toggle); // expand — focus moves to the panel heading
    await waitFor(() => {
      expect(document.activeElement?.className).toContain('assistant-label');
    });
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
