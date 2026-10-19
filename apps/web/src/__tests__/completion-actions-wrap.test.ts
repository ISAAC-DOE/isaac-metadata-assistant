/*
 * THE FINISHED COMPLETE SCREEN'S BUTTON ROW WRAPS — QA item 10 (2026-10-12).
 *
 * Measured in Chromium at 390px: `.completion-actions` (two buttons, `display: flex`,
 * no wrap) had scrollWidth 484 against a 368px main column, so the second button ran
 * off the screen. jsdom computes no layout, so this pins the RULE that prevents it;
 * the browser measurement is in the slice report.
 */
import { describe, it, expect } from 'vitest';

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const screensCss = (): string =>
  (Object.entries(cssFiles).find(([path]) => path.endsWith('/screens/screens.css'))?.[1] ?? '').replace(
    /\/\*[\s\S]*?\*\//g,
    '',
  );

function declarationsOf(selector: string): string {
  const src = screensCss();
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = new RegExp(`(?:^|\\n)\\s*${escaped}\\s*\\{([^}]*)\\}`).exec(src);
  return match?.[1] ?? '';
}

describe('.completion-actions at narrow widths', () => {
  it('the row wraps instead of overflowing the column', () => {
    expect(screensCss().length).toBeGreaterThan(1000);
    expect(declarationsOf('.completion-actions')).toMatch(/flex-wrap:\s*wrap/);
  });

  it('a button may wrap its own label rather than force the row wider than the column', () => {
    const rule = declarationsOf('.completion-actions > .btn');
    expect(rule).toMatch(/max-width:\s*100%/);
    expect(rule).toMatch(/white-space:\s*normal/);
  });
});
