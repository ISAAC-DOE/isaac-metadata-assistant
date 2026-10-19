/**
 * THE STATUS FILTER IS A RADIO GROUP, SO IT BEHAVES LIKE ONE (review, 2026-10-18).
 *
 * The facets became the "What Needs Me?" headline as figure-first tiles, and the
 * re-review measured three defects in that change, each pinned here:
 *
 * 1. EVERY RADIO WAS A TAB STOP. A radio group is ONE stop in the tab sequence
 *    (the checked radio); the arrow keys move between its members and select as
 *    they go, and Home / End reach the ends (APG radio group). Seven tab stops
 *    for one choice is seven presses to get past it.
 * 2. THE ACCESSIBLE NAME READ "Needs Attention , 5 of all experiments" in a
 *    real browser: the label and the screen-reader count were two flex items,
 *    and Chromium separates flex items with a space, so the comma that began the
 *    second one landed after a space. jsdom joins them without one, so a name
 *    assertion alone passes over the defect — the second test therefore also
 *    asserts the name is not assembled from a fragment that begins with a comma.
 * 3. THE TILES SCROLLED SIDEWAYS at phone width (a 310px row in 208–278px), and
 *    `layout-widths` forbids a sideways-scrolling region. The rule is read from
 *    the stylesheet, because jsdom computes no layout.
 */
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { LibraryFacets } from '../components/LibraryToolbar';
import type { LibraryFacetId } from '../lib/library';

const COUNTS: Record<LibraryFacetId, number> = {
  all: 5,
  needsAttention: 3,
  proposals: 0,
  inReview: 0,
  ready: 1,
  draft: 4,
  done: 0,
};

function Harness({ variant = 'tiles' as 'tiles' | 'chips', initial = 'all' as LibraryFacetId }) {
  const [facet, setFacet] = useState<LibraryFacetId>(initial);
  return (
    <>
      <LibraryFacets facet={facet} onFacet={setFacet} counts={COUNTS} variant={variant} />
      <output data-testid="facet">{facet}</output>
    </>
  );
}

const radios = () => screen.getAllByRole('radio');
const names = () => radios().map((r) => r.getAttribute('aria-label') ?? r.textContent);

describe.each(['tiles', 'chips'] as const)('the %s status filter', (variant) => {
  it('is ONE tab stop: only the checked radio is in the tab sequence', () => {
    render(<Harness variant={variant} initial="ready" />);
    const tabbable = radios().filter((r) => r.tabIndex === 0);
    expect(tabbable).toHaveLength(1);
    expect(tabbable[0]).toHaveAttribute('aria-checked', 'true');
    for (const r of radios()) if (r !== tabbable[0]) expect(r.tabIndex).toBe(-1);
  });

  it('MUTATION-GUARDED: the arrow keys move focus AND the selection, and wrap', () => {
    render(<Harness variant={variant} />);
    const group = screen.getByRole('radiogroup');
    const order = radios();
    order[0].focus();

    fireEvent.keyDown(order[0], { key: 'ArrowRight' });
    expect(document.activeElement).toBe(radios()[1]);
    expect(radios()[1]).toHaveAttribute('aria-checked', 'true');
    expect(radios()[1].tabIndex).toBe(0);
    expect(radios()[0].tabIndex).toBe(-1);

    fireEvent.keyDown(radios()[1], { key: 'ArrowDown' });
    expect(document.activeElement).toBe(radios()[2]);

    fireEvent.keyDown(radios()[2], { key: 'ArrowUp' });
    fireEvent.keyDown(radios()[1], { key: 'ArrowLeft' });
    expect(document.activeElement).toBe(radios()[0]);

    // Wraps from the first to the last, and back.
    fireEvent.keyDown(radios()[0], { key: 'ArrowLeft' });
    expect(document.activeElement).toBe(radios()[order.length - 1]);
    expect(radios()[order.length - 1]).toHaveAttribute('aria-checked', 'true');
    fireEvent.keyDown(radios()[order.length - 1], { key: 'ArrowRight' });
    expect(document.activeElement).toBe(radios()[0]);
    expect(group).toBeInTheDocument();
  });

  it('Home and End reach the first and last radio', () => {
    render(<Harness variant={variant} />);
    radios()[1].focus();
    fireEvent.keyDown(radios()[1], { key: 'End' });
    expect(document.activeElement).toBe(radios()[radios().length - 1]);
    expect(screen.getByTestId('facet').textContent).toBe('all');
    fireEvent.keyDown(radios()[radios().length - 1], { key: 'Home' });
    expect(document.activeElement).toBe(radios()[0]);
    expect(radios()[0]).toHaveAttribute('aria-checked', 'true');
  });

  it('names each radio "<label>, <count> of all experiments", with no space before the comma', () => {
    render(<Harness variant={variant} />);
    expect(screen.getByRole('radio', { name: 'Needs Attention, 3 of all experiments' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Ready to Export, 1 of all experiments' })).toBeInTheDocument();
    for (const n of names()) expect(n).not.toMatch(/\s,/);
    // The defect's own shape: the name must not depend on joining a fragment that
    // BEGINS with a comma to the label — Chromium puts a space at that seam.
    for (const r of radios()) {
      for (const el of Array.from(r.querySelectorAll('*'))) {
        expect((el.textContent ?? '').trimStart().startsWith(','), el.outerHTML).toBe(false);
      }
    }
  });
});

describe('the status filter at phone width', () => {
  const css = readFileSync(resolve(__dirname, '../components/library.css'), 'utf8').replace(
    /\/\*[\s\S]*?\*\//g,
    '',
  );
  it('wraps rather than scrolling sideways (no horizontal scroller on the facets)', () => {
    const rules = [...css.matchAll(/([^{}]*\.library-facets[^{}]*)\{([^{}]*)\}/g)];
    expect(rules.length).toBeGreaterThan(0);
    for (const [, selector, body] of rules) {
      expect(body, selector.trim()).not.toMatch(/overflow-x\s*:\s*(auto|scroll)/);
      expect(body, selector.trim()).not.toMatch(/flex-wrap\s*:\s*nowrap/);
    }
  });
});
