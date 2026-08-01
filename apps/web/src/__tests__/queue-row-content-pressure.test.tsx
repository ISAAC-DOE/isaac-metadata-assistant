/*
 * M1 — the queue row starved its own text at phone widths.
 *
 * MEASURED defect (Chromium, production build, /experiments). `.exp-trailing` is
 * `flex: none` and measures 180.4px at EVERY width — it never shrinks, because
 * its "N Fields Need You" chip is 150.4px of nowrap text. `.exp-main` was
 * `flex: 1` (flex-basis 0) with `min-width: 0`, so it received only
 * rowContent − 196.4. On the two rows carrying that chip:
 *
 *   width   .exp-main   .exp-title cw/sw (height)   .exp-scenario-text cw/sw (h)   row height
 *    640       332          332/332  (h22.5)              200/200  (h15.5)            102
 *    390        82           82/82   (h89.9)               65/65   (h62.1)            264
 *    375        67           67/67   (h89.9)               50/50   (h77.6)          279.5
 *    320        12           12/67   (h157.3)               0/8    (h481)           767.4
 *
 * At 320 that is not truncation — the title wrapped into a 12px column at one
 * character per line, and the scenario line reached zero visible width in a
 * 481px-tall box. The three rows WITHOUT the chip were never affected (174px at
 * 320) and are unchanged by the fix.
 *
 * AFTER (same build, same probe):
 *
 *   width   .exp-main   .exp-title cw/sw (height)   .exp-scenario-text cw/sw (h)   row height
 *    640       332          332/332  (h22.5)              200/200  (h15.5)            102   ← identical
 *    390       278          278/278  (h22.5)              200/200  (h15.5)            137
 *    375       263          263/263  (h22.5)              200/200  (h15.5)            137
 *    320       208          208/208  (h44.9)              191/191  (h31)               175
 *
 * THE FIX IS A FLOOR PLUS A WRAP, NOT A BREAKPOINT — and that is the thing this
 * file guards. A media query would have to guess which rows carry a wide
 * trailing chip; the row can decide for itself. Raising `.exp-main`'s
 * `min-width` from 0 to 160px raises its hypothetical main size from 0 to 160,
 * so flexbox breaks the line exactly when main + gap + trailing stops fitting.
 * Measured consequence, sweeping 320→768:
 *   · a row WITH the chip wraps at 320–460 and stays inline from 470 up
 *     (160 + 16 + 180.4 = 356.4 against the row's content box);
 *   · a row with only the chevron never wraps, down to 320
 *     (160 + 16 + 18 = 194 against 210px of content there);
 *   · 640 / 768 / 1024 / 1280 do not wrap at all and are byte-identical.
 * Every term in those sums is a fixed pixel value — padding, gap, an 18px icon —
 * so the margin does not move with the system font.
 *
 * HONESTY NOTE: jsdom applies no layout and evaluates no media query. Nothing
 * below measures a pixel. The assertions are CSS-source guards over the authored
 * stylesheet plus DOM assertions about what React renders; the geometry above is
 * the browser evidence.
 */

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { ExperimentRow } from '../components/ExperimentRow';
import type { ExperimentSummary } from '../lib/types';

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const cssByName = (name: string): string =>
  Object.entries(cssFiles).find(([path]) => path.endsWith(`/${name}`))?.[1] ?? '';

const stripComments = (source: string): string => source.replace(/\/\*[\s\S]*?\*\//g, '');

/** Everything OUTSIDE any at-rule — each `@…{…}` removed by brace matching. */
function withoutAtRules(source: string): string {
  const src = stripComments(source);
  let out = '';
  for (let i = 0; i < src.length; i += 1) {
    if (src[i] !== '@') {
      out += src[i];
      continue;
    }
    const open = src.indexOf('{', i);
    if (open < 0) break;
    let depth = 0;
    let j = open;
    for (; j < src.length; j += 1) {
      if (src[j] === '{') depth += 1;
      else if (src[j] === '}') {
        depth -= 1;
        if (depth === 0) break;
      }
    }
    i = j;
  }
  return out;
}

function rulesIn(source: string): { selector: string; body: string }[] {
  return [...source.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    selector: m[1].trim().replace(/\s+/g, ' '),
    body: m[2],
  }));
}

const queue = cssByName('queue.css');
const baseRules = rulesIn(withoutAtRules(queue));
const ruleFor = (selector: string): string | undefined =>
  baseRules.find((r) => r.selector === selector)?.body;

const px = (body: string | undefined, prop: string): number | undefined => {
  const m = new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*(-?[\\d.]+)px`).exec(body ?? '');
  return m ? Number(m[1]) : undefined;
};

const needsAttention: ExperimentSummary = {
  id: '01SYNTH1',
  title: 'Synthetic XANES — CuO (Cu K-edge)',
  technique: 'Cu K-edge XANES',
  idOrDraft: 'draft',
  lifecycle: 'draft',
  date: { iso: '2026-07-12', display: 'Jul 12, 2026', accessible: 'Created July 12, 2026' },
  scenario: 'Scenario 1 · seeded: extraction only',
  group: 'needsAttention',
  trailing: { needsYouCount: 5 },
} as ExperimentSummary;

const chevronOnly: ExperimentSummary = {
  ...needsAttention,
  id: '01SYNTH3',
  group: 'inReview',
  trailing: {},
};

function renderRow(exp: ExperimentSummary) {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ExperimentRow exp={exp} />
    </MemoryRouter>,
  );
}

describe('M1 · the queue row breaks its line instead of starving its text', () => {
  it('CSS source: the row may wrap', () => {
    const row = ruleFor('.exp-row');
    expect(row, 'queue.css must declare .exp-row').toBeDefined();
    expect(row!).toMatch(/flex-wrap:\s*wrap/);
  });

  it('CSS source: .exp-main has a floor, and it is NOT min-width: 0', () => {
    const main = ruleFor('.exp-main');
    expect(main, 'queue.css must declare .exp-main').toBeDefined();
    const floor = px(main, 'min-width');
    expect(floor, '.exp-main must declare a min-width floor').toBeDefined();
    // `min-width: 0` is the defect: it let this column be handed 12px AND kept
    // the row's hypothetical size at 0 so the line never broke.
    expect(floor!).toBeGreaterThan(0);
    // Comfortably clear of the 24px "meaningful visible fragment" threshold the
    // browser probe uses.
    expect(floor!).toBeGreaterThanOrEqual(120);
    // …and bounded ABOVE, which is the half that is easy to lose: a row whose
    // trailing side is only the 18px chevron must still fit one line at 320px,
    // where the row's content box is 210px and the gap is 16px.
    expect(floor! + 16 + 18).toBeLessThanOrEqual(210);
  });

  it('CSS source: the fix needs no breakpoint — the row decides for itself', () => {
    // Both declarations live outside every at-rule. If someone later moves them
    // into a media query, the wrap stops tracking the row's ACTUAL trailing
    // content and starts guessing from the viewport.
    expect(ruleFor('.exp-row')).toMatch(/flex-wrap:\s*wrap/);
    expect(px(ruleFor('.exp-main'), 'min-width')).toBeDefined();
    expect(stripComments(queue)).not.toMatch(/@media/);
  });

  it('CSS source: the trailing side was NOT made to shrink instead', () => {
    // Shrinking `.exp-trailing` would squeeze its own nowrap chip text and just
    // relocate the defect; the row wraps instead, and the trailing block keeps
    // its intrinsic size.
    const trailing = ruleFor('.exp-trailing');
    expect(trailing, 'queue.css must declare .exp-trailing').toBeDefined();
    expect(trailing!).toMatch(/flex:\s*none/);
    expect(ruleFor('.exp-chevron')!).toMatch(/flex:\s*none/);
  });

  it('CSS source: the wrapped line gets its own row gap', () => {
    // `gap: 16px` would otherwise apply between the wrapped lines too.
    const row = ruleFor('.exp-row')!;
    expect(row).toMatch(/row-gap:\s*\d+px/);
    expect(px(row, 'row-gap')!).toBeLessThan(px(row, 'gap') ?? 16);
  });

  it('CSS source: the children keep their own shrink protections', () => {
    // The floor bounds the COLUMN; a pathological unbroken token is still the
    // children's problem, and their existing guards must survive.
    expect(ruleFor('.exp-scenario')!).toMatch(/min-width:\s*0/);
    expect(ruleFor('.exp-scenario-text')!).toMatch(/min-width:\s*0/);
    expect(ruleFor('.exp-scenario-text')!).toMatch(/overflow-wrap:\s*anywhere/);
    expect(ruleFor('.exp-scenario-icon')!).toMatch(/flex:\s*none/);
  });

  it('DOM: the wide trailing chip that forces the wrap is really rendered there', () => {
    const { container } = renderRow(needsAttention);
    const trailing = container.querySelector('.exp-trailing')!;
    const chip = trailing.querySelector('.chip')!;
    expect(chip).not.toBeNull();
    expect(chip.textContent).toContain('Fields Need You');
    // …and the row that has no such chip is the one that must never wrap
    const { container: plain } = renderRow(chevronOnly);
    expect(plain.querySelector('.exp-trailing .chip')).toBeNull();
    expect(plain.querySelector('.exp-trailing .exp-chevron')).not.toBeNull();
  });

  it('DOM: the row is still ONE link, with its accessible name intact', () => {
    const { container } = renderRow(needsAttention);
    const row = container.querySelector('.exp-row')!;
    // Wrapping must not split the click target or change the semantics.
    expect(row.tagName).toBe('A');
    expect(row.getAttribute('href')).toBe('/record/01SYNTH1');
    expect(container.querySelectorAll('a').length).toBe(1);
    const name = row.getAttribute('aria-label')!;
    expect(name).toContain('Synthetic XANES — CuO (Cu K-edge)');
    expect(name).toContain('Scenario 1 · seeded: extraction only');
    expect(name).toContain('5 fields need you');
    // both text blocks the defect destroyed are inside that one link
    expect(row.querySelector('.exp-title')!.textContent).toBe('Synthetic XANES — CuO (Cu K-edge)');
    expect(row.querySelector('.exp-scenario-text')!.textContent).toBe(
      'Scenario 1 · seeded: extraction only',
    );
  });
});
