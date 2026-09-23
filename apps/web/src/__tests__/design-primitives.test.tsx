/*
 * THE SHARED STATE AND DISCLOSURE PRIMITIVES (2026-09-22): `SemanticStatus`,
 * `HelpTip` and `Disclosure`. Each is small; each carries an accessibility or
 * honesty rule that a future caller could quietly break, and those rules are what
 * is pinned here.
 */

import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';

import { SEMANTIC_STATUS, SemanticStatus, type SemanticState } from '../components/SemanticStatus';
import { HelpTip, placeHelpTip } from '../components/HelpTip';
import { Disclosure } from '../components/Disclosure';

const cssFiles = import.meta.glob('../components/{semantic-status,help-tip,disclosure}.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;
const css = (name: string) =>
  Object.entries(cssFiles).find(([path]) => path.endsWith(`${name}.css`))![1];

describe('SemanticStatus', () => {
  const ALL = Object.keys(SEMANTIC_STATUS) as SemanticState[];

  it('covers exactly the owner’s thirteen states, each with a word and an icon', () => {
    expect(ALL.sort()).toEqual(
      [
        'awaitingJudgment',
        'complete',
        'conflict',
        'inherited',
        'invalid',
        'missing',
        'needsReview',
        'notApplicable',
        'notShownHere',
        'ready',
        'sourcesAgree',
        'unavailable',
        'unmapped',
      ].sort(),
    );
    for (const state of ALL) {
      const { container, unmount } = render(<SemanticStatus state={state} />);
      const chip = container.querySelector('.semantic-status')!;
      // NEVER COLOUR ALONE: an icon AND a word, every time.
      expect(chip.querySelector('svg[aria-hidden="true"]'), state).not.toBeNull();
      expect(chip.textContent?.trim(), state).toBe(SEMANTIC_STATUS[state].label);
      unmount();
    }
  });

  it('a caller may reword a state but never change its tone or shape', () => {
    const { container } = render(<SemanticStatus state="unavailable" label="Locked" />);
    const chip = container.querySelector('.semantic-status')!;
    expect(chip.textContent).toBe('Locked');
    expect(chip.getAttribute('data-tone')).toBe('neutral');
    expect(chip.getAttribute('data-state')).toBe('unavailable');
  });

  it('uses no RESERVED verdict green: success is the verified teal, on white', () => {
    const src = css('semantic-status');
    expect(src).not.toMatch(/--pass-/);
    const success = /\[data-tone='success'\]\s*\{([^}]*)\}/.exec(src)![1];
    expect(success).toMatch(/--verified-text/);
    // `--verified-text` on its own tint is the recorded 4.21:1 exception; on
    // `--surface` it clears AA, so the pill sits on white.
    expect(success).toMatch(/background:\s*var\(--surface\)/);
  });

  it('a Missing value is drawn with a dashed edge — shape, not only hue', () => {
    expect(css('semantic-status')).toMatch(/\[data-state='missing'\]\s*\{[^}]*border-style:\s*dashed/);
  });
});

describe('HelpTip', () => {
  it('is a NAMED button that opens on press, never on hover alone', () => {
    render(
      <HelpTip subject="Temperature">
        <p>Temperature for this Run. Stored in kelvin.</p>
      </HelpTip>,
    );
    const trigger = screen.getByRole('button', { name: 'About Temperature' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    const panelId = trigger.getAttribute('aria-controls')!;
    const panel = document.getElementById(panelId)!;
    // `aria-controls` never dangles: the panel is in the DOM while closed.
    expect(panel).not.toBeNull();
    expect(panel.hidden).toBe(true);

    fireEvent.mouseEnter(trigger);
    fireEvent.pointerEnter(trigger);
    expect(panel.hidden, 'hover alone opened it').toBe(true);

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(panel.hidden).toBe(false);
    expect(panel.textContent).toContain('Stored in kelvin');
  });

  it('Escape closes it and returns focus to the trigger', () => {
    render(<HelpTip subject="Run">definition</HelpTip>);
    const trigger = screen.getByRole('button', { name: 'About Run' });
    fireEvent.click(trigger);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(document.activeElement).toBe(trigger);
  });

  it('a press outside closes it; a press inside does not', () => {
    render(
      <>
        <button type="button">elsewhere</button>
        <HelpTip subject="Run">
          <p>definition</p>
        </HelpTip>
      </>,
    );
    const trigger = screen.getByRole('button', { name: 'About Run' });
    fireEvent.click(trigger);
    const panel = document.getElementById(trigger.getAttribute('aria-controls')!)!;
    fireEvent.pointerDown(panel);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    fireEvent.pointerDown(screen.getByRole('button', { name: 'elsewhere' }));
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  /* ── review #277, I-2: flip, clamp, z-order, focus-leave ─────────────────── */

  it('opens BELOW the trigger when the panel fits there', () => {
    const p = placeHelpTip({ top: 100, bottom: 124, left: 100, width: 24 }, 80, { width: 390, height: 844 });
    expect(p.placement).toBe('below');
    expect(p.top).toBe(130);
  });

  it('FLIPS ABOVE when it would pass the bottom edge (the 390px fold case)', () => {
    // A trigger near the bottom of an 844px viewport, a 120px panel: below would end
    // at 900 > 836, so it goes above the trigger instead.
    const p = placeHelpTip({ top: 770, bottom: 794, left: 40, width: 24 }, 120, { width: 390, height: 844 });
    expect(p.placement).toBe('above');
    expect(p.top).toBe(770 - 6 - 120);
    expect(p.top + 120).toBeLessThanOrEqual(844 - 8);
  });

  it('CLAMPS inside the viewport when neither side holds it whole, never above the top', () => {
    const p = placeHelpTip({ top: 60, bottom: 84, left: 10, width: 24 }, 400, { width: 320, height: 420 });
    // Below would end at 490 > 412 and above would start at -346, so it is pulled up
    // just far enough to end on the bottom limit: 412 - 400 = 12, never above 8.
    expect(p.top).toBe(12);
    // Horizontally: 8px inside both edges at 320px.
    expect(p.left).toBeGreaterThanOrEqual(8);
    expect(p.left + p.width).toBeLessThanOrEqual(320 - 8);
  });

  it('clamps horizontally at the right edge', () => {
    const p = placeHelpTip({ top: 100, bottom: 124, left: 370, width: 24 }, 60, { width: 390, height: 844 });
    expect(p.left + p.width).toBeLessThanOrEqual(390 - 8);
  });

  it('closes when focus LEAVES the trigger and panel, not when it moves between them', () => {
    render(
      <>
        <HelpTip subject="Run">
          <span>definition</span>
        </HelpTip>
        <button type="button">next control</button>
      </>,
    );
    const trigger = screen.getByRole('button', { name: 'About Run' });
    const panel = document.getElementById(trigger.getAttribute('aria-controls')!)!;
    fireEvent.click(trigger);
    // Trigger → panel: still open (a press inside the panel moves focus there).
    fireEvent.blur(trigger, { relatedTarget: panel });
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    // Panel → the next control (a Tab away): closed, so it cannot cover the next label.
    fireEvent.blur(panel, { relatedTarget: screen.getByRole('button', { name: 'next control' }) });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('paints above the floating Assistant pill', () => {
    const src = css('help-tip');
    const z = /\.helptip-panel\s*\{[^}]*z-index:\s*(\d+)/.exec(src);
    expect(z).not.toBeNull();
    // `.assistant-drawer-trigger` is 45, its backdrop 46, the drawer 47.
    expect(Number(z![1])).toBeGreaterThan(47);
  });

  it('draws a visible focus ring and no verdict hue in any interaction state', () => {
    const src = css('help-tip');
    expect(src).toMatch(/\.helptip-trigger:focus-visible\s*\{[^}]*outline:\s*2px solid/);
    expect(src).not.toMatch(/--pass-|--fail-/);
  });
});

describe('Disclosure', () => {
  it('the WHOLE ROW is one button carrying aria-expanded and aria-controls', () => {
    render(
      <Disclosure summary="How ISAAC Reads Your Notes" meta="3 examples">
        <p>body text</p>
      </Disclosure>,
    );
    const trigger = screen.getByRole('button', { name: /How ISAAC Reads Your Notes/ });
    expect(trigger).toHaveAccessibleName('How ISAAC Reads Your Notes 3 examples');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    const body = document.getElementById(trigger.getAttribute('aria-controls')!)!;
    // Closed content is HIDDEN, not unmounted: still in the DOM for every guard.
    expect(body.hidden).toBe(true);
    expect(body.textContent).toBe('body text');
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(body.hidden).toBe(false);
  });

  it('keeps state inside it across a collapse, because it never unmounts its body', () => {
    function Box() {
      const [text, setText] = useState('');
      return <input aria-label="inner" value={text} onChange={(e) => setText(e.target.value)} />;
    }
    render(
      <Disclosure summary="Record Locally Instead" defaultOpen>
        <Box />
      </Disclosure>,
    );
    fireEvent.change(screen.getByLabelText('inner'), { target: { value: 'kept' } });
    const trigger = screen.getByRole('button', { name: /Record Locally Instead/ });
    fireEvent.click(trigger);
    fireEvent.click(trigger);
    expect((screen.getByLabelText('inner') as HTMLInputElement).value).toBe('kept');
  });

  it('can title a section: headingLevel wraps the button in a heading', () => {
    render(
      <Disclosure summary="Details of This Reading" headingLevel={3}>
        x
      </Disclosure>,
    );
    const heading = screen.getByRole('heading', { level: 3, name: /Details of This Reading/ });
    expect(heading.querySelector('button')).not.toBeNull();
  });

  it('has hover, focus-visible and expanded treatments, and a turn that reduced motion stops', () => {
    const src = css('disclosure');
    expect(src).toMatch(/\.disclosure-trigger:hover\s*\{/);
    expect(src).toMatch(/\.disclosure-trigger:focus-visible\s*\{[^}]*outline:\s*2px solid/);
    expect(src).toMatch(/\.is-open[^{]*\.disclosure-chevron\s*\{[^}]*rotate\(90deg\)/);
    // The turn is a `transition`, which `base.css` neutralises under
    // `prefers-reduced-motion` for every element (`interaction-states.test.ts`).
    expect(src).toMatch(/\.disclosure-chevron\s*\{[^}]*transition:/);
  });
});
