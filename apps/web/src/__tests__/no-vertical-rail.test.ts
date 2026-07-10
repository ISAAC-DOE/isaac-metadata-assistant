import { describe, it, expect } from 'vitest';

/*
 * The No-Vertical-Rail rule (no-vertical-rail-rule.md) is permanent and
 * system-wide: no thick colored left/right border used as a status/accent rail.
 *
 * This scan fails on any `border-left`/`border-right` declaration paired with a
 * STATUS or ACCENT color. Neutral region dividers (a full 1px `var(--border)`
 * separating LeftNav / WorkflowSpine / EvidenceTrail / right-panel from the
 * canvas) are the ONLY allowed border-left/right, and they are NOT rails.
 *
 * Allowed exceptions: neutral `--border*` tokens + `transparent`/`currentColor`.
 * Expected count of accent rails: 0.
 *
 * CSS/TSX sources are pulled in as raw strings via Vite's import.meta.glob, so
 * no node:fs (and no @types/node) is needed.
 */

const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const tsxFiles = import.meta.glob('../**/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

// Accent / status colors that must never appear on a left/right border.
const ACCENT =
  /(--action|--assist|--pass|--fail|--advisory|--needsyou|--verified|--confirmed|--inferred|--processing|--cited|--idle|--src-|--cover-text|--selected-row|#[0-9a-fA-F]{3,8}|\b(?:green|red|amber|blue|indigo)\b)/;

describe('no colored vertical rails', () => {
  it('no src/**/*.css uses a colored border-left/border-right (status/accent rail)', () => {
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(cssFiles)) {
      source.split('\n').forEach((line, i) => {
        if (/border-(?:left|right)(?:-color)?\s*:/.test(line) && ACCENT.test(line)) {
          offenders.push(`${path}:${i + 1}  ${line.trim()}`);
        }
      });
    }
    expect(offenders, `colored vertical rails found:\n${offenders.join('\n')}`).toEqual([]);
  });

  it('no inline style in *.tsx sets a colored borderLeft/borderRight', () => {
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(tsxFiles)) {
      source.split('\n').forEach((line, i) => {
        if (/border(?:Left|Right)(?:Color)?\s*:/.test(line) && ACCENT.test(line)) {
          offenders.push(`${path}:${i + 1}  ${line.trim()}`);
        }
      });
    }
    expect(offenders, `inline colored rails found:\n${offenders.join('\n')}`).toEqual([]);
  });
});
