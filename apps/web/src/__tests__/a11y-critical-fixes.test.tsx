/*
 * The two CRITICAL accessibility defects the real-browser baseline found
 * (`docs/browser-accessibility-testing.md` §6 A11Y-02 / A11Y-03, recorded as
 * A1 / A2 in the Baseline Completion Matrix §3B), closed and locked.
 *
 * These are unit-level guards. The authoritative measurement stays in the
 * Playwright + axe sweep, where the two rules are now expected to produce ZERO
 * nodes because their entries were deleted from `e2e/a11y-baseline.ts`. What
 * this file adds is a FAST guard that fails in seconds — and, for A1, one that
 * reproduces the breakpoint condition jsdom cannot reach by media query.
 *
 * The axe assertions below run the real axe-core engine over the rendered
 * markup, restricted to the exact rules that were failing. jsdom has no layout,
 * so only DOM/ARIA-shape rules like these are meaningful here; nothing
 * geometric (contrast, scrollable regions) is asserted in this file.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axe from 'axe-core';

import { TopBar } from '../components/TopBar';
import { EvidenceTrailPanel } from '../components/EvidenceTrailPanel';
import type { EvidenceTrailEntry } from '../lib/types';

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Run axe-core over a container, restricted to named rules. */
async function axeRules(container: HTMLElement, rules: string[]) {
  const results = await axe.run(container, {
    runOnly: { type: 'rule', values: rules },
    resultTypes: ['violations'],
  });
  return results.violations.map((v) => `${v.id} × ${v.nodes.length}`);
}

/* ───────────────────────────── A1 · button-name ──────────────────────────── */

function renderTopBar() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <TopBar variant="home" />
    </MemoryRouter>,
  );
}

/**
 * `chrome.css`'s `@media (max-width: 640px)` block sets
 * `.topbar-search-label, .topbar-search-kbd { display: none }`. jsdom evaluates
 * no media query and lays nothing out, so the breakpoint is reproduced here by
 * applying the SAME declaration the media query applies. That is the condition
 * under test — not an approximation of it.
 */
function collapseToPhoneWidth(container: HTMLElement) {
  container
    .querySelectorAll<HTMLElement>('.topbar-search-label, .topbar-search-kbd')
    .forEach((el) => {
      el.style.display = 'none';
    });
}

describe('A1 · the global search trigger keeps its accessible name below the 640px breakpoint', () => {
  it('has an accessible name at desktop width', () => {
    const { container } = renderTopBar();
    const trigger = container.querySelector<HTMLButtonElement>('button.topbar-search')!;
    expect(trigger).not.toBeNull();
    expect(trigger).toHaveAccessibleName('Search');
  });

  it('STILL has an accessible name once the media query hides the label and the ⌘K hint', () => {
    const { container } = renderTopBar();
    const trigger = container.querySelector<HTMLButtonElement>('button.topbar-search')!;

    collapseToPhoneWidth(container);

    // Precondition: the visible text really is gone, i.e. the collapse worked.
    expect(container.querySelector('.topbar-search-label')).not.toBeVisible();
    expect(container.querySelector('.topbar-search-kbd')).not.toBeVisible();

    // The defect: before the fix this computed to '' — the button had NO name.
    expect(trigger).toHaveAccessibleName('Search');
  });

  it('names the button from an attribute, not from content that CSS can hide', () => {
    const { container } = renderTopBar();
    const trigger = container.querySelector<HTMLButtonElement>('button.topbar-search')!;

    // The durable part of the fix: the name source survives any stylesheet.
    expect(trigger.getAttribute('aria-label')).toBe('Search');
    // …and the icon stays out of the name.
    expect(trigger.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
  });

  it('does not double-announce where the visible label IS shown', () => {
    const { container } = renderTopBar();
    const trigger = container.querySelector<HTMLButtonElement>('button.topbar-search')!;

    // Visible label present…
    expect(container.querySelector('.topbar-search-label')).toBeVisible();
    // …and the name is still exactly one "Search", never "Search Search ⌘K".
    const name = trigger.getAttribute('aria-label')!;
    expect(name).toBe('Search');
    expect(name.toLowerCase().match(/search/g)).toHaveLength(1);
  });

  it('axe reports no button-name violation in the TopBar at phone width', async () => {
    const { container } = renderTopBar();
    collapseToPhoneWidth(container);
    expect(await axeRules(container, ['button-name'])).toEqual([]);
  });
});

/* ─────────────────────── A2 · Evidence Trail role/state ──────────────────── */

const entry = (
  key: string,
  namespaced: boolean,
  resolved: boolean,
): EvidenceTrailEntry => ({
  key,
  label: key,
  value: 'synthetic',
  status: 'verified',
  sourceTypes: ['file_listing'],
  evidence: [],
  namespaced,
  resolved,
});

const ENTRIES: EvidenceTrailEntry[] = [
  entry('record_type', false, true),
  entry('sample.sample_id', false, true),
  entry('measurement.technique', false, false),
  entry('assets:raw_listing', true, false),
  entry('implicit:absorbing_element', true, false),
];

function renderTrail(selectedKey = ENTRIES[0].key) {
  const onSelect = vi.fn();
  const view = render(
    <EvidenceTrailPanel
      entries={ENTRIES}
      directTotal={3}
      selectedKey={selectedKey}
      onSelect={onSelect}
      meta={{ schema_version: '1.05', generated_utc: '2026-01-01T00:00:00Z' }}
    />,
  );
  return { ...view, onSelect };
}

describe('A2 · Evidence Trail entries are real buttons whose selected state is exposed', () => {
  it('never puts aria-pressed on a listitem', () => {
    const { container } = renderTrail();
    // The exact defect: `<button role="listitem" aria-pressed="…">`.
    expect(container.querySelectorAll('[role="listitem"][aria-pressed]')).toHaveLength(0);
    expect(container.querySelectorAll('button[role="listitem"]')).toHaveLength(0);
  });

  it('keeps the list semantics on the wrapper and the button semantics on the control', () => {
    const { container, getAllByRole } = renderTrail();

    // Two `role="list"` groups (Direct Fields, Namespaced), one listitem per entry.
    expect(getAllByRole('list')).toHaveLength(2);
    expect(getAllByRole('listitem')).toHaveLength(ENTRIES.length);

    // Every listitem's interactive child is a NATIVE <button type="button">,
    // which is what guarantees Enter/Space activation and Tab reachability
    // without any custom key handling.
    const items = getAllByRole('listitem');
    for (const item of items) {
      const btn = item.querySelector<HTMLButtonElement>(':scope > button.trail-entry');
      expect(btn).not.toBeNull();
      expect(btn!.tagName).toBe('BUTTON');
      expect(btn!.getAttribute('type')).toBe('button');
      expect(btn!.hasAttribute('role')).toBe(false);
      expect(btn!.disabled).toBe(false);
    }

    // …and every entry is reachable as a button.
    expect(container.querySelectorAll('button.trail-entry')).toHaveLength(ENTRIES.length);
  });

  it('exposes selected AND unselected state on every entry', () => {
    const { container } = renderTrail('measurement.technique');
    const buttons = [...container.querySelectorAll<HTMLButtonElement>('button.trail-entry')];

    expect(buttons.map((b) => b.getAttribute('aria-pressed'))).toEqual([
      'false',
      'false',
      'true',
      'false',
      'false',
    ]);
    // Exactly one pressed — the trail always has a selection.
    expect(buttons.filter((b) => b.getAttribute('aria-pressed') === 'true')).toHaveLength(1);
    // The visual selected class tracks the same entry it announces.
    expect(buttons[2].classList.contains('selected')).toBe(true);
  });

  it('keeps selection behaviour: activating an entry reports its key', () => {
    const { container, onSelect } = renderTrail();
    const buttons = [...container.querySelectorAll<HTMLButtonElement>('button.trail-entry')];

    fireEvent.click(buttons[1]);
    expect(onSelect).toHaveBeenCalledWith('sample.sample_id');

    // Namespaced entries are selectable too.
    fireEvent.click(buttons[3]);
    expect(onSelect).toHaveBeenCalledWith('assets:raw_listing');
  });

  it('keeps keyboard access: every entry is tabbable, focusable and key-activated', () => {
    const { container, onSelect } = renderTrail();
    const buttons = [...container.querySelectorAll<HTMLButtonElement>('button.trail-entry')];

    for (const btn of buttons) {
      // No tabindex="-1" and no roving-tabindex scheme: plain Tab order, in
      // DOM order, which is the whole point of the list-of-buttons pattern.
      expect(btn.hasAttribute('tabindex')).toBe(false);
      btn.focus();
      expect(document.activeElement).toBe(btn);
    }

    // jsdom does not synthesise the click a real browser fires for Enter/Space
    // on a native button, so the browser behaviour is asserted through the
    // element contract above and reproduced here explicitly: a keydown that a
    // browser would turn into a click must reach the same handler.
    const target = buttons[2];
    target.focus();
    fireEvent.keyDown(target, { key: 'Enter', code: 'Enter' });
    fireEvent.click(target); // what the browser does in response to that keydown
    expect(onSelect).toHaveBeenCalledWith('measurement.technique');

    onSelect.mockClear();
    fireEvent.keyDown(target, { key: ' ', code: 'Space' });
    fireEvent.keyUp(target, { key: ' ', code: 'Space' });
    fireEvent.click(target); // ditto, on key-up, for Space
    expect(onSelect).toHaveBeenCalledWith('measurement.technique');
  });

  it('axe reports no aria-allowed-attr / aria-allowed-role violation on the trail', async () => {
    const { container } = renderTrail();
    expect(await axeRules(container, ['aria-allowed-attr', 'aria-allowed-role'])).toEqual([]);
  });
});
