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
import { HelpTip } from '../components/HelpTip';
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
