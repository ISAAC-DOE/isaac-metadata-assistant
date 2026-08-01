/*
 * I3 — evidence-trail selection was conveyed by colour alone.
 *
 * MEASURED before (Chromium, /record/<id>/evidence, focus removed so only the
 * selection channels remain):
 *   selected background #f5f9fd vs the #fbfcfd panel  → 1.03:1
 *   selected border     #cfe0f2 vs the selected bg    → 1.27:1
 *   selected border     #cfe0f2 vs the panel          → 1.31:1
 * WCAG 2.1 SC 1.4.11 asks 3:1 of the visual information required to identify a
 * component STATE, so no channel carried it — in greyscale the selected row is
 * the same row.
 *
 * MEASURED after, same page and build:
 *   marker #2c6ab0 vs the selected row background     → 5.23:1
 *   marker #2c6ab0 vs the #fbfcfd panel               → 5.39:1
 *   `.trail-key` left edge, selected vs unselected    → 83 and 83 (no shift)
 *   `aria-pressed`                                    → "true" / "false", as before
 * Focus is a separate treatment and both can be seen at once: tabbing onto the
 * selected row measured `outline: solid 2px rgb(44,106,176) off:2px` AND
 * `border-left`-free marker background rgb(44,106,176), with :focus-visible true.
 *
 * WHY A DOT AND NOT THE OBVIOUS LEADING BAR: a >=3px coloured left edge is
 * banned system-wide by design-handoff/05-design-system/no-vertical-rail-rule.md
 * — which names the selected evidence row as its case 4, and also forbids
 * "a full coloured border that reads as a rail". A small filled disc is one of
 * that document's approved replacements. `no-vertical-rail.test.ts` enforces it
 * and caught the first attempt at this fix.
 *
 * HONESTY NOTE: jsdom neither lays out nor rasterises anything. The ratios below
 * are recomputed here from the AUTHORED token values (arithmetic, not a
 * measurement) and the pixel figures above are the browser evidence.
 */

import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';

import { EvidenceTrailPanel } from '../components/EvidenceTrailPanel';
import type { EvidenceTrailEntry } from '../lib/types';

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const cssByName = (name: string): string =>
  Object.entries(cssFiles).find(([path]) => path.endsWith(`/${name}`))?.[1] ?? '';

const stripComments = (source: string): string => source.replace(/\/\*[\s\S]*?\*\//g, '');

function rulesIn(source: string): { selector: string; body: string }[] {
  return [...stripComments(source).matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    selector: m[1].trim().replace(/\s+/g, ' '),
    body: m[2],
  }));
}

const evidence = cssByName('evidence.css');
const ruleFor = (selector: string): string | undefined =>
  rulesIn(evidence).find((r) => r.selector === selector)?.body;

/** A token's authored hex, read out of tokens.css. */
function token(name: string): string {
  const m = new RegExp(`${name}\\s*:\\s*(#[0-9a-fA-F]{3,8})`).exec(cssByName('tokens.css'));
  if (!m) throw new Error(`token ${name} not found in tokens.css`);
  return m[1];
}

function relativeLuminance(hex: string): number {
  const h = hex.replace('#', '');
  const rgb = [0, 1, 2].map((i) => parseInt(h.slice(i * 2, i * 2 + 2), 16) / 255);
  const lin = rgb.map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
}

function contrast(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Synthetic, unmistakably fake trail entries — the same shape the sidecar
 *  produces. Selection is a CONTROLLED prop on this panel, so the state is
 *  asserted by rendering it, and the click contract by the callback. */
const entry = (key: string, namespaced: boolean): EvidenceTrailEntry => ({
  key,
  label: key,
  value: 'synthetic',
  status: 'verified',
  sourceTypes: ['file_listing'],
  evidence: [],
  namespaced,
  resolved: true,
});

const ENTRIES: EvidenceTrailEntry[] = [
  entry('record_type', false),
  entry('sample.sample_id', false),
  entry('assets:raw_listing', true),
];

function renderTrail(selectedKey: string) {
  const onSelect = vi.fn();
  const view = render(
    <EvidenceTrailPanel
      entries={ENTRIES}
      directTotal={2}
      selectedKey={selectedKey}
      onSelect={onSelect}
      meta={{ schema_version: '1.05', generated_utc: '2099-01-01T00:00:00Z' }}
    />,
  );
  return { ...view, onSelect };
}

describe('I3 · selection carries a non-colour channel', () => {
  it('CSS source: every entry reserves a marker slot, so selecting shifts nothing', () => {
    const before = ruleFor('.trail-entry::before');
    expect(before, 'evidence.css must declare .trail-entry::before').toBeDefined();
    expect(before!).toMatch(/content:\s*''/);
    expect(before!).toMatch(/background:\s*transparent/);
    expect(before!).toMatch(/border-radius:\s*50%/);
    expect(before!).toMatch(/flex:\s*none/);
    // A reserved slot only works if it has a fixed size in BOTH states.
    expect(before!).toMatch(/width:\s*6px/);
    expect(before!).toMatch(/height:\s*6px/);
  });

  it('CSS source: the selected state paints that marker, and changes no geometry', () => {
    const marker = ruleFor('.trail-entry.selected::before');
    expect(marker, 'the selected marker must be declared').toBeDefined();
    expect(marker!).toMatch(/background:\s*var\(--action\)/);
    // Anything below would move the row's content on selection.
    for (const prop of ['width', 'height', 'padding', 'margin', 'border-width']) {
      expect(marker!, `selection must not change ${prop}`).not.toMatch(new RegExp(`${prop}\\s*:`));
    }
    const selected = ruleFor('.trail-entry.selected')!;
    for (const prop of ['padding', 'border-width', 'font-size', 'gap']) {
      expect(selected, `selection must not change ${prop}`).not.toMatch(new RegExp(`${prop}\\s*:`));
    }
  });

  it('the marker meets SC 1.4.11 against BOTH adjacent colours', () => {
    const marker = token('--action');
    const rowBackground = token('--selected-row-bg'); // the colour it sits in
    const panel = token('--surface-subtle'); // the colour it sits against
    expect(contrast(marker, rowBackground)).toBeGreaterThanOrEqual(3);
    expect(contrast(marker, panel)).toBeGreaterThanOrEqual(3);
    // …and the record of WHY this was needed: the two pre-existing channels do
    // not, and this test fails the day someone "simplifies" back to them.
    expect(contrast(rowBackground, panel)).toBeLessThan(3);
    expect(contrast(token('--action-selected-border'), rowBackground)).toBeLessThan(3);
  });

  it('CSS source: selection does not borrow the focus treatment', () => {
    // base.css draws :focus-visible as a 2px offset outline. Selection must stay
    // a different shape, so a focused selected row shows both.
    for (const selector of ['.trail-entry.selected', '.trail-entry.selected::before']) {
      expect(ruleFor(selector) ?? '').not.toMatch(/outline/);
    }
    expect(stripComments(cssByName('base.css'))).toMatch(
      /:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--action\)/,
    );
  });

  it('CSS source: the marker is inert to assistive technology', () => {
    // `content: ''` — an empty string, so no pseudo-element text is exposed and
    // nothing competes with aria-pressed.
    expect(ruleFor('.trail-entry::before')!).toMatch(/content:\s*''\s*;/);
    expect(ruleFor('.trail-entry.selected::before')!).not.toMatch(/content:/);
  });

  it('DOM: aria-pressed is still the programmatic channel, on the same element as the marker', () => {
    const { container } = renderTrail(ENTRIES[1].key);
    const entries = [...container.querySelectorAll<HTMLButtonElement>('.trail-entry')];
    expect(entries).toHaveLength(ENTRIES.length);

    const pressed = entries.filter((e) => e.getAttribute('aria-pressed') === 'true');
    expect(pressed).toHaveLength(1);
    // ONE element carries BOTH channels: the `.selected` class the visual marker
    // hangs off, and the ARIA state. Neither replaced the other.
    expect(pressed[0].classList.contains('selected')).toBe(true);
    expect(pressed[0].textContent).toContain(ENTRIES[1].key);
    for (const other of entries.filter((e) => e !== pressed[0])) {
      expect(other.getAttribute('aria-pressed')).toBe('false');
      expect(other.classList.contains('selected')).toBe(false);
    }
  });

  it('DOM: the state moves with the selection, and activating a row still reports it', () => {
    const first = renderTrail(ENTRIES[0].key);
    const firstEntries = [...first.container.querySelectorAll('.trail-entry')];
    expect(firstEntries[0].getAttribute('aria-pressed')).toBe('true');
    expect(firstEntries[1].getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(firstEntries[1]);
    expect(first.onSelect).toHaveBeenCalledWith(ENTRIES[1].key);

    // …and with that selection applied, the marker's class follows it.
    const second = renderTrail(ENTRIES[1].key);
    const secondEntries = [...second.container.querySelectorAll('.trail-entry')];
    expect(secondEntries[0].classList.contains('selected')).toBe(false);
    expect(secondEntries[1].classList.contains('selected')).toBe(true);
  });
});
